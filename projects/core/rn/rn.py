#!/usr/bin/env python

#Author: Dustin Darcy (dustindarcy@gmail.com)
#        ChatGPT adaptation of rn.pl (https://chat.openai.com/chat/5f5d9d2b-8008-4679-9c3b-b496e8ccfe9f) 
#Date: 2023/02/19
#Description: Rename files using a regular expression
#Usage: rename python-regex-match python-regex-replace [filenames]

# TODO: 
# 1. modify massedit.py in repos so that it can rename files (already does sed like operations on files)

import argparse
import glob
import os
import re
import sys


class HelpParser(argparse.ArgumentParser):
    # https://stackoverflow.com/questions/4042452/display-help-message-with-python-argparse-when-script-is-called-without-any-argu
    def error(self, message):
        sys.stderr.write('**ERROR**: %s\n\n' % message) 
        self.print_help()
        sys.exit(2)

#Formatter class from: https://stackoverflow.com/questions/61324536/python-argparse-with-argumentdefaultshelpformatter-and-rawtexthelpformatter
class MultiHelpFormatter( argparse.RawTextHelpFormatter, argparse.ArgumentDefaultsHelpFormatter ): 
    pass

# class SmartFormatter(argparse.HelpFormatter):
#     def _split_lines(self, text, width):
#         if text.startswith('R|'):
#             return text[2:].splitlines()
#         # this is the RawTextHelpFormatter._split_lines
#         return argparse.HelpFormatter._split_lines(self, text, width)
    

def main(args):
    match_regex = args.regex
    replace_regex = args.replacement
    filenames = glob.glob(" ".join(args.filenames))

    iter = 0
    regex = match_regex

    if(args.debug): 
        print(f"Regex: {regex} ... Replacement: {replace_regex}")

    for filename in filenames:
        new_name = filename
        if(args.debug): print(f"Renaming {filename}...")
        while os.path.exists(filename):
            temp_replace_regex = replace_regex
            if "\\q" in replace_regex:
                temp_replace_regex = replace_regex.replace("\\q", str(iter))
                if(args.debug): print(f"Replacing \\q with {iter} in {temp_replace_regex}")
                iter += 1
            try:
            	#DONE: create another version where we use re.sub from 2 parameters (first: matching regex, second: replacement string)
            	#Dustin: Create a version that allows a person to pass in the entire re.sub() function as a string
                new_name = re.sub(regex, temp_replace_regex, filename) 
            except Exception as e:
                print(f"Failed to rename {filename}: {e}")
                break

            if(args.debug): print(f"New name: {new_name}")
            if new_name == filename:
                break

            os.rename(filename, new_name)

            if not args.quiet:
                print(f"Renamed {filename} to {new_name}")

        if filename == new_name:
                print(f"Could not rename {filename}")

    if args.debug:
        print("Done.")

help_text = '''Example usage:

rn.py "(.*?)\\.(.*\$)" "\\g<1>_\\q\\.\\g<2>" *.EXT
       (FILENA.EXT) (FILENA\\q.EXT) *.EXT

Notes:
\\q acts as a built-in incrementer. So if you have a series of files and 
the goal is to number them, you could use a regular expression to pass 
the arguments in, in a sorted manner.
'''

if __name__ == '__main__':
    parser = HelpParser(description='Rename files using a regular expression', add_help=True, epilog=help_text, formatter_class=MultiHelpFormatter)
    parser.add_argument('regex', help='regex for the match pattern')
    parser.add_argument('replacement', help='replacement string for matched patterns')
    parser.add_argument('filenames', nargs='+', help='list of filenames to apply the renaming')
    parser.add_argument('-q', '--quiet', action='store_true', help='quiet output')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose output')
    parser.add_argument('-d', '--debug', action='store_true', help='debug output')
    parser.add_argument('--version', action='version', version="%(prog)s v0.5 -- Multiplatform Python Renamer, see github.com/djdarcy", help='display version information')

    args = parser.parse_args()
    main(args)