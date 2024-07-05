#!/bin/bash

# Function to check if a file is binary
is_binary() {
    if [[ $(file --mime-type -b "$1") == application* || $(file --mime-type -b "$1") == image* || $(file --mime-type -b "$1") == audio* || $(file --mime-type -b "$1") == video* ]]; then
        return 0
    else
        return 1
    fi
}

# Function to check if a compressed file contains binary files
check_compressed_binary() {
    local temp_dir=$(mktemp -d)
    unzip -qq "$1" -d "$temp_dir"
    flag=1
    for local_file in $(find $temp_dir -type f -not -path '*/.git/*')
    do
        if is_binary "$local_file"; then
            # echo "Binary file found in $1: $(echo $local_file | cut -d'/' -f4-)"
            flag=0
        fi
    done

    rm -rf "$temp_dir"
    return $flag
}

# Main script
project_name=$(basename $1 | sed 's/\.git$//') > /dev/null
if [ ! -e "$project_name" ]; then
    git clone $1 > /dev/null 2>&1
fi

for file in $(find $project_name -type f -not -path '*/.git/*' -not -path '*/test/*')
do
    if [ ! -e "$file" ]; then
        continue
    fi

    if [[ $(file --mime-type -b "$file") == application/zip || $(file --mime-type -b "$file") == application/x-tar ]]; then
        if check_compressed_binary "$file"; then
            echo "Binary archive found: $file"
        fi
    elif is_binary "$file"; then
        echo "Binary file found: $file"
    fi
done
# rm -rf $project_name
