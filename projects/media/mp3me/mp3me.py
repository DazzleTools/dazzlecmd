#!/usr/bin/env python3
# -*- coding: utf-8 -*-

##############################################################
# mp3me - Convert FLAC to mp3, create torrent.
##############################################################

import os
import re
import fnmatch
import shutil
import unicodedata
from optparse import OptionParser
import threading
import sys

VERSION = "3.5.2"

### BEGIN CONFIGURATION ###

# Output folder unless specified: ("/home/user/Desktop/")
#output = os.path.join(os.environ['HOME'], "Desktop/")
output = os.getcwd()

# Separate torrent output folder (defaults to output):
torrent_dir = output

# Do you want to move additional files (.jpg, .log, etc)?
moveother = 1

# Do you want to zeropad tracknumbers? (1 => 01, 2 => 02 ...)
zeropad = 1

# Do you want to dither FLACs to 16/44 before encoding?
dither = 0

# Specify tracker announce URL (e.g. "http://tracker.example.org:34000/"),
# or pass it at runtime with --tracker. Empty = no torrent created.
tracker = ""

# Specify torrent passkey via --passkey (never hard-code a real one here).
# Empty = no torrent created.
passkey = ""

# Max number of threads (ex: Normal: 1, Dual-core = 2, Hyperthreaded Dual-core = 4)
max_threads = 1

# Default encoding options
enc_options = {
	'320':	{'enc': 'lame',  	'opts': '-b 320 --ignore-tag-errors'},
	'V0':	{'enc': 'lame',		'opts': '-V 0 --vbr-new --ignore-tag-errors'},
	'V2':	{'enc': 'lame',		'opts': '-V 2 --vbr-new --ignore-tag-errors'},
	'Q8':	{'enc': 'oggenc',	'opts': '-q 8'},
	'AAC':	{'enc': 'neroAacEnc',	'opts': '-br 320000'},
	'ALAC':	{'enc': 'ffmpeg',	'opts': '-i - -acodec alac'},
	'FLAC': {'enc': 'flac',		'opts': '--best'}
}

### END CONFIGURATION ###

codecs = []

# os.system() and os.popen() have issues with `
def escape_backtick(pattern):
	pattern = re.sub('`', r'\`', pattern)
	return pattern

def escape_quote(pattern):
	pattern = re.sub('"', '\\"', pattern)
	return pattern

def sanitize_character(char, string, replacement=None):
	if replacement is None:
		return string.split(char)[0]
	else: 
		return string.replace(char, replacement)

	# semicolon_index = string.find(char)
	# print(str(semicolon_index) + " " + char)
	# if semicolon_index != -1:
	# 	if(replacement != None):
	# 		string = string[:semicolon_index] + replacement + string[semicolon_index+1:]
	# 	else:
	# 		string = string[:semicolon_index]
	# return string

def remove_characters(char, string):
	for c in char:
		semicolon_index = string.find(c)
		if semicolon_index != -1:
			string = string[:semicolon_index]
	return string

class Transcode(threading.Thread):
	def __init__(self, file, flacdir, mp3_dir, codec, options, cv):
		threading.Thread.__init__(self)
		self.file = file
		self.flacdir = flacdir
		self.mp3_dir = mp3_dir
		self.codec = codec
		self.options = options
		self.cv = cv

	def run(self):
		tags = {}
		for tag in ('TITLE', 'ALBUM', 'ARTIST', 'TRACKNUMBER', 'GENRE', 'COMMENT', 'DATE'):
			tagcommand = 'metaflac --show-tag=' + escape_quote(tag) + ' "' + escape_quote(self.file) + '"'
			temp = re.sub(r'\S.*=', '', os.popen(escape_backtick(tagcommand)).read().rstrip())
			#temp = remove_character(";", temp)	# Remove semicolon from end of tag
			temp = remove_characters(["\n", "\r"], temp) # Remove newline
			#print(temp) #debug
			tags.update({tag:temp})
			del temp

		if self.options.zeropad and len(tags['TRACKNUMBER']) == 1:
			tags['TRACKNUMBER'] = '0' + tags['TRACKNUMBER']

		# Partial fix: some track titles contain the U+2215 DIVISION SLASH, a
		# unicode look-alike for "/" that breaks path handling. Replace it.
		# (A genuine "/" path separator inside a title is still unhandled.)
		bad_character = "∕"
		mp3_filename = re.sub(re.escape(self.flacdir), self.mp3_dir, self.file)
		print(mp3_filename)
		mp3_filename = sanitize_character(bad_character, mp3_filename, "-")
		print(mp3_filename)
		mp3_filename = re.sub(r'\.flac$', '', mp3_filename)
		if not os.path.exists(os.path.dirname(mp3_filename)):
			os.makedirs(os.path.dirname(mp3_filename))

		flac_command = ''

		if enc_options[self.codec]['enc'] == 'lame':
			flac_command = 'lame -S %s --tt "%s" --tl "%s" --ta "%s" --tn "%s" --tg "%s" --ty "%s" --add-id3v2 - "%s.mp3" 2>&1'
		elif enc_options[self.codec]['enc'] == 'oggenc':
			flac_command = 'oggenc -Q %s -t "%s" -l "%s" -a "%s" -N "%s" -G "%s" -d "%s" -o "%s.ogg" - 2>&1'
		elif enc_options[self.codec]['enc'] == 'ffmpeg':
			flac_command = 'ffmpeg %s -metadata title="%s" -metadata album="%s" -metadata author="%s" -metadata track="%s" -metadata genre="%s" -metadata date="%s" "%s.m4a" 2>&1'
		elif enc_options[self.codec]['enc'] == 'neroAacEnc':
			flac_command = 'neroAacEnc %s -if - -of "%s.m4a" 2>&1 && neroAacTag "%s.m4a" -meta:title="%s" -meta:album="%s" -meta:artist="%s" -meta:track="%s" -meta:genre="%s" -meta:year="%s"'
		elif enc_options[self.codec]['enc'] == 'flac':
			flac_command = 'flac %s -s -T "TITLE=%s" -T "ALBUM=%s" -T "ARTIST=%s" -T "TRACKNUMBER=%s" -T "GENRE=%s" -T "DATE=%s" -o "%s.flac" - 2>&1'

		if self.options.dither:
			flac_command = 'sox -t wav - -b 16 -t wav - rate 44100 dither | ' + flac_command

		print(mp3_filename)
		flac_command = 'flac -dc -- "' + escape_quote(self.file) + '" | ' + flac_command

		if enc_options[self.codec]['enc'] == 'neroAacEnc':
			flac_command = flac_command % (escape_quote(enc_options[self.codec]['opts']), escape_quote(mp3_filename), escape_quote(mp3_filename), escape_quote(tags['TITLE']), escape_quote(tags['ALBUM']), escape_quote(tags['ARTIST']), escape_quote(tags['TRACKNUMBER']), escape_quote(tags['GENRE']), escape_quote(tags['DATE']))
		else:
			flac_command = flac_command % (escape_quote(enc_options[self.codec]['opts']), escape_quote(tags['TITLE']), escape_quote(tags['ALBUM']), escape_quote(tags['ARTIST']), escape_quote(tags['TRACKNUMBER']), escape_quote(tags['GENRE']), escape_quote(tags['DATE']), escape_quote(mp3_filename))

		if self.options.verbose:
			print(escape_backtick(flac_command))
		os.system(escape_backtick(flac_command))

		self.cv.acquire()
		self.cv.notify_all()
		self.cv.release()

		return 0

def add_enc_option(option, opt, value, parser):
	codecs.append(opt[2:])

def main(argv=None):
	# Parse options and arguments
	usage_text = "%prog [options] [--320 --V2 --Q8 --AAC ...] /path/to/FLAC"
	info_text = "Depends on flac, metaflac, mktorrent, and optionally oggenc, lame, neroAacEnc, neroAacTag, mp3gain, aacgain, vorbisgain, and sox."
	parser = OptionParser(prog="mp3me", usage=usage_text, version="%prog " + VERSION, epilog=info_text)
	parser.add_option('-v', '--verbose',	action='store_true',	dest='verbose',		default=False,	help='increase verbosity (Default: False)')
	parser.add_option('-n', '--notorrent',	action='store_true',	dest='notorrent',	default=False,	help='will not create a torrent after conversion (Default: False)')
	parser.add_option('--nolog',		action='store_true',	dest='nolog',		default=False,	help='will not move log files after conversion (Default: False)')
	parser.add_option('--nocue',		action='store_true',	dest='nocue',		default=False,	help='will not move cue files after conversion (Default: False)')
	parser.add_option('-m', '--moveother',	action='store_true',	dest='moveother',	default=moveother,	help='move additional files (Default: True)')
	parser.add_option('-p', '--passkey',	dest='passkey',		default=passkey,	help='tracker PASSKEY', metavar='PASSKEY')
	parser.add_option('-t', '--tracker',	dest='tracker',		default=tracker,	help='tracker announce URL (no default; required for torrent creation)', metavar='URL')
	parser.add_option('-o', '--output',	dest='output',		default=output,		help='set the output PATH', metavar='PATH')
	parser.add_option('--torrent-dir',	dest='torrent_dir',	default=torrent_dir,	help='set independent torrent output directory')
	parser.add_option('-z', '--zeropad',	action='store_true',	dest='zeropad',		default=zeropad,	help='zeropad track numbers (Default: True)')
	parser.add_option('-r', '--replaygain',	action='store_true',	dest='replaygain',	default=False,	help='add ReplayGain to new files (Default: False)')
	parser.add_option('-d', '--dither',	action='store_true',	dest='dither',		default=dither,	help='dither FLACs to 16/44 before encoding (Default: False)')
	parser.add_option('--threads',		type="int",		dest='max_threads',	default=max_threads,	help='set number of threads THREADS (Default: 1)', metavar='THREADS')
	parser.add_option('-c', '--original',	action='store_true',	dest='original',	default=False,	help='create a torrent for the original FLAC')

	for enc_opt in enc_options.keys():
		parser.add_option("--" + enc_opt, action="callback", callback=add_enc_option, help='convert to %s' % (enc_opt))

	(options, flacdirs) = parser.parse_args(args=argv)

	if len(flacdirs) < 1:
		parser.error("Incorrect number of arguments")

	if not options.output.endswith('/'):
		options.output += '/'

	if len(codecs) == 0 and not options.original:
		print('You need to provide at least one format to transcode to (320, V0, Q8 ...)')
		return 1

	for flacdir in flacdirs:
		flacdir = os.path.abspath(flacdir)
		flacfiles = []

		for dirpath, dirs, files in os.walk(flacdir, topdown=False):
			for name in files:
				if fnmatch.fnmatch(name, '*.flac'):
					flacfiles.append(os.path.join(dirpath, name))
		if options.original:
			print('Working with FLAC...')

			if options.output and options.passkey and options.tracker and not options.notorrent:
				if options.verbose: print('Creating torrent...')
				torrent_command = 'mktorrent -p -a %s/announce -o "%s.torrent" "%s"' % (options.tracker + options.passkey, escape_quote(options.output + os.path.basename(flacdir)), escape_quote(flacdir))
				if options.verbose: print(escape_backtick(torrent_command))
				os.system(escape_backtick(torrent_command))

			print('Finished working with FLAC')

		for codec in codecs:
			mp3_dir = options.output + os.path.basename(flacdir)
			if 'FLAC' in flacdir:
				mp3_dir = re.sub(re.compile('FLAC', re.I), codec, mp3_dir)
			else:
				mp3_dir = mp3_dir + " (" + codec + ")"
			if not os.path.exists(mp3_dir):
				os.makedirs(mp3_dir)

			print('Encoding with ' + codec + ' started...')

			threads = []
			cv = threading.Condition()
			for file in flacfiles:
				cv.acquire()
				while((threading.activeCount() == options.max_threads + 1) or (options.max_threads == 0 and threading.activeCount() == 2)):
					cv.wait()
				cv.release()
				t=Transcode(file, flacdir, mp3_dir, codec, options, cv)
				t.start()
				threads.append(t)

			for t in threads:
				t.join()

			print('\nEncoding with ' + codec + ' finished.')

			if options.moveother:
				if options.verbose: print('Moving other files...')
				for dirpath, dirs, files in os.walk(flacdir, topdown=False):
					for name in files:
						if options.nolog and fnmatch.fnmatch(name, '*.log'):
							continue
						if options.nocue and fnmatch.fnmatch(name, '*.cue'):
							continue
						if not fnmatch.fnmatch(name, '*.flac') and not fnmatch.fnmatch(name, '*.m3u'):
							d = re.sub(re.escape(flacdir), mp3_dir, dirpath)
							if not os.path.exists(d):
								os.makedirs(d)
							shutil.copy(os.path.join(dirpath, name), d)

			if options.replaygain and enc_options[codec]['enc'] != 'flac':
				if options.verbose: print('Applying replay gain...')

				for dirpath, dirs, files in os.walk(mp3_dir, topdown=False):
					for name in dirs:
						if enc_options[codec]['enc'] == 'lame':
							os.system(escape_backtick('mp3gain -q -c -s i "' + os.path.join(dirpath, name) + '"/*.mp3'))
						if enc_options[codec]['enc'] == 'oggenc':
							os.system(escape_backtick('vorbisgain -qafrs "' + os.path.join(dirpath, name) + '"/*.ogg'))
						if enc_options[codec]['enc'] == 'neroAacEnc':
							os.system(escape_backtick('aacgain -q -c "' + os.path.join(dirpath, name) + '"/*.m4a'))

			if options.output and options.passkey and options.tracker and not options.notorrent:
				if options.verbose: print('Creating torrent...')
				torrent_command = 'mktorrent -p -a %s/announce -o "%s.torrent" "%s"' % (options.tracker + options.passkey, escape_backtick(options.torrent_dir + os.path.basename(mp3_dir)), mp3_dir)
				if options.verbose: print(escape_backtick(torrent_command))
				os.system(escape_backtick(torrent_command))

		if options.verbose: print('All done with ' + flacdir + ' ...')
	return 0

if __name__ == '__main__':
	sys.exit(main())
