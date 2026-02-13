import os
import subprocess
import sys
import re
import pyperclip
import argparse

def find_in_path(file_name):
    """Search for a file in the system PATH and return all unique matches."""
    matches = []
    path_dirs = os.getenv('PATH').split(os.pathsep)
    for dir in path_dirs:
        potential_path = os.path.join(dir, file_name)
        if os.path.isfile(potential_path):
            matches.append(os.path.abspath(potential_path))
    return matches

def get_executable_path_from_command(command):
    """Run a command and return the actual executable path."""
    try:
        # Run the command and capture output
        proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.communicate()
        # Return the executable path if the process was created successfully
        if proc.returncode == 0:
            return subprocess.check_output(f"where {command.split()[0]}", shell=True).decode().strip().split('\n')[0]
    except Exception as e:
        if args.verbose:
            print(f"Error running command: {e}")
    return None

def update_path(selected_path):
    """Update the PATH environment variable to swap positions of the selected and highest priority paths."""
    old_path = os.getenv('PATH')
    path_dirs = old_path.split(os.pathsep)
    
    selected_dir = os.path.dirname(selected_path).lower()
    highest_priority_path = matches[0]
    highest_priority_dir = os.path.dirname(highest_priority_path).lower()

    path_dirs_lower = [p.lower() for p in path_dirs]

    if selected_dir in path_dirs_lower and highest_priority_dir in path_dirs_lower:
        selected_index = path_dirs_lower.index(selected_dir)
        highest_priority_index = path_dirs_lower.index(highest_priority_dir)

        # Swap positions
        path_dirs[selected_index], path_dirs[highest_priority_index] = path_dirs[highest_priority_index], path_dirs[selected_index]

        new_path_value = os.pathsep.join(path_dirs)
        os.environ['PATH'] = new_path_value
        return old_path, new_path_value
    else:
        raise ValueError(f"Could not find {selected_dir} or {highest_priority_dir} in PATH.")

def copy_to_clipboard(new_path):
    """Copy new path to clipboard, prompt if clipboard is not empty."""
    clipboard_content = pyperclip.paste()
    if clipboard_content:
        prompt = input("Clipboard is not empty. Overwrite? (y/n): ")
        if prompt.lower() != 'y':
            return
    pyperclip.copy(new_path)
    if args.verbose:
        print("New PATH copied to clipboard.")

def write_path_to_file(old_path, new_path):
    """Write the old and new PATH to files for easy reference."""
    with open("old_path.txt", "w") as f:
        f.write(old_path)
    with open("new_path.txt", "w") as f:
        f.write(new_path)

def extract_version_info(file_path, version_flags):
    """Extract version information from the executable output."""
    version_info = None
    for flag in version_flags:
        try:
            result = subprocess.run([file_path, flag], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            output = result.stdout + result.stderr
            lines = output.splitlines()[:5]
            for line in lines:
                match = re.search(r'\b\d+(\.\d+){0,2}\b', line)
                if match:
                    version_info = match.group()
                    break
            if version_info:
                break
        except Exception as e:
            if args.verbose:
                print(f"Error extracting version info: {e}")
    return version_info

def main():
    """Main function to find the file in PATH or running processes."""
    parser = argparse.ArgumentParser(description="Find and manage executables in the PATH.")
    parser.add_argument('filename', type=str, help="The name of the file to search for.")
    parser.add_argument('--select', '-s', type=int, help="Select the nth instance of the executable found in the PATH.")
    parser.add_argument('--version', type=str, nargs='?', const='--version', help="Flag to extract version information (default: --version).")
    parser.add_argument('--verbose', '-v', action='store_true', help="Enable verbose mode with detailed output.")

    global args
    args = parser.parse_args()
    file_name = args.filename
    command_name = re.sub(r'\.exe$|\.sh$|\.bat$', '', file_name, flags=re.IGNORECASE)
    command = command_name
    select_index = args.select
    version_flags = [args.version] if args.version else ["--version", "-version", "-h", "--help"]

    # Try to find the file in PATH
    global matches
    matches = find_in_path(file_name)
    if matches:
        if args.verbose:
            print(f"Found {file_name} in the following PATH locations:")
        for idx, match in enumerate(matches, 1):
            version_info = extract_version_info(match, version_flags)
            version_str = f" (version: {version_info})" if version_info else ""
            print(f"{idx}: {match}{version_str}")
    else:
        if args.verbose:
            print(f"{file_name} not found in PATH.")

    # Try running the command to check if it matches the path
    if args.verbose:
        print(f"Trying to run the command to verify the executable location...")
    executable_path = get_executable_path_from_command(command)
    if executable_path:
        version_info = extract_version_info(executable_path, version_flags)
        version_str = f" (version: {version_info})" if version_info else ""
        if args.verbose:
            print(f"Found {file_name} running at: {executable_path}{version_str}")
        if executable_path not in matches:
            if args.verbose:
                print(f"Note: The running executable was not found in the PATH locations above.")
    else:
        if args.verbose:
            print(f"Could not find {file_name} in running processes.")

    if matches and select_index is not None:
        try:
            selected_path = matches[select_index - 1]
            old_path, new_path = update_path(selected_path)
            if args.verbose:
                print(f"\nOld PATH:\n{old_path}")
                print(f"\nNew PATH:\n{new_path}")
                print(f"\nUpdated PATH to prioritize: {selected_path}")

            # Copy new path to clipboard
            copy_to_clipboard(new_path)

            # Write paths to files
            write_path_to_file(old_path, new_path)
        except IndexError:
            if args.verbose:
                print(f"Invalid selection index: {select_index}")
        except ValueError as ve:
            if args.verbose:
                print(ve)

if __name__ == "__main__":
    main()
