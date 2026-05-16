#!/bin/bash

# DLNAencoder Install Script

set -e

echo "Starting DLNAencoder installation..."

# 1. Dependency Check
echo "Checking dependencies..."

deps=("ffmpeg" "ffprobe" "cpupower" "python3")
missing_deps=()

for cmd in "${deps[@]}"; do
    if ! command -v "$cmd" &> /dev/null; then
        missing_deps+=("$cmd")
    fi
done

if [ ${#missing_deps[@]} -ne 0 ]; then
    echo "Error: The following dependencies are missing: ${missing_deps[*]}"
    exit 1
fi

if ! python3 -c "import psutil" &> /dev/null; then
    echo "Error: python3 'psutil' library is not available."
    exit 1
fi

echo "Dependencies satisfied."

# 2. Directory Setup
echo "Setting up directories..."
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.config/DLNAencoder"

# 3. File Deployment
echo "Deploying files..."
cp "/home/matthewh/Projects/DLNAencoder/DLNAencoder.py" "$HOME/.local/bin/DLNAencoder"
chmod +x "$HOME/.local/bin/DLNAencoder"

# 4. Shell Integration
echo "Setting up shell integration..."

# Alias to add
ALIAS_CMD="alias encode='python3 ~/.local/bin/DLNAencoder'"

add_alias_to_file() {
    local file="$1"
    if [ -f "$file" ]; then
        if ! grep -qF "$ALIAS_CMD" "$file"; then
            echo "" >> "$file"
            echo "# DLNAencoder alias" >> "$file"
            echo "$ALIAS_CMD" >> "$file"
            echo "Added alias to $file"
        else
            echo "Alias already exists in $file"
        fi
    fi
}

# Identify shell and existing config files
if [ -n "$BASH_VERSION" ] || [ -f "$HOME/.bashrc" ]; then
    add_alias_to_file "$HOME/.bashrc"
fi

if [ -n "$ZSH_VERSION" ] || [ -f "$HOME/.zshrc" ]; then
    add_alias_to_file "$HOME/.zshrc"
fi

# 5. Final Message
echo ""
echo "Installation complete!"
echo "Please restart your shell or run 'source ~/.bashrc' (or ~/.zshrc) to use the 'encode' command."
