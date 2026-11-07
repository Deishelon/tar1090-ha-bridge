#!/bin/bash

# Exit on error
set -e

# Get the directory where the script is located
REPO_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
USER_NAME=$(whoami)
SERVICE_NAME="tar1090-ha-bridge"
VENV_DIR="$REPO_DIR/venv"
PYTHON_BIN="$VENV_DIR/bin/python"

echo "Setting up $SERVICE_NAME..."

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Install/Update dependencies
echo "Installing/Updating dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$REPO_DIR/src/requirements.txt"

# Create .env file if it doesn't exist (to help user configure it)
if [ ! -f "$REPO_DIR/.env" ]; then
    echo "Creating template .env file..."
    cp "$REPO_DIR/.env.example" "$REPO_DIR/.env"
    echo "Please edit $REPO_DIR/.env with your configuration."
fi

# Generate systemd service file
echo "Generating systemd service file..."
SERVICE_FILE_CONTENT="[Unit]
Description=tar1090 to Home Assistant Bridge
After=network.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$REPO_DIR
Environment=\"PATH=$VENV_DIR/bin\"
ExecStart=$PYTHON_BIN $REPO_DIR/src/main.py $REPO_DIR/.env
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target"

echo "$SERVICE_FILE_CONTENT" | sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null

# Reload systemd and enable service
echo "Reloading systemd and enabling service..."
sudo systemctl daemon-reload

echo "Setup complete!"
echo "To start the service, run: sudo systemctl start $SERVICE_NAME"
echo "To make service auto-run, run: sudo systemctl enable $SERVICE_NAME"
echo "To view logs, run: journalctl -u $SERVICE_NAME -f"
echo "Note: Make sure to edit $REPO_DIR/.env with your tar1090 and MQTT details before starting."
