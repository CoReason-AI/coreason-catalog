#!/bin/bash
set -e

OPA_VERSION="v0.61.0"
OPA_URL="https://openpolicyagent.org/downloads/${OPA_VERSION}/opa_linux_amd64_static"

echo "Installing OPA ${OPA_VERSION}..."

if [ -f "/usr/local/bin/opa" ]; then
    echo "OPA already installed."
    exit 0
fi

curl -L -o opa "${OPA_URL}"
chmod +x opa

# Install to /usr/local/bin if root, else output to bin/
if [ "$(id -u)" -eq 0 ]; then
    mv opa /usr/local/bin/opa
    echo "OPA installed to /usr/local/bin/opa"
else
    mkdir -p bin
    mv opa bin/opa
    echo "OPA downloaded to bin/opa"
fi
