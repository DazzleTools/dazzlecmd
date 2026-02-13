import argparse
import re
import sys

def split_text(separator=';', token=None):
    # Read input from stdin
    input_text = sys.stdin.read().strip()

    # Split the text based on the specified separator
    result = input_text.split(separator)

    # Check if a token for searching is provided
    if token:
        # Construct regex pattern for broad, case-insensitive matching
        regex_pattern = f".*{re.escape(token)}.*"
        # Compile the regular expression pattern with IGNORECASE flag
        pattern = re.compile(regex_pattern, re.IGNORECASE)

        # Filter items containing the token and print
        filtered_result = [item for item in result if pattern.search(item)]
        for item in filtered_result:
            print(item)
    else:
        # If no token is provided, print all items
        for item in result:
            print(item)

if __name__ == "__main__":
    # Create argument parser
    parser = argparse.ArgumentParser(description="Split text based on the specified separator and optionally search for a token within items.")

    # Add arguments
    parser.add_argument("--separator", "-s", default=';', help="Separator character (default: ';')")
    parser.add_argument("--find", "-f", help="Token to filter the text by, case-insensitive")

    # Parse the command-line arguments
    args = parser.parse_args()

    # Call split_text function with the specified arguments
    split_text(args.separator, args.find)

