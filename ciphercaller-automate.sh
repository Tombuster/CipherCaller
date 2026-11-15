#!/bin/bash

# Check arguments
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <rounds per KEM>"
    exit 1
fi

kems=("ML-KEM-512" "ML-KEM-768" "ML-KEM-1024" "HQC-1" "HQC-3" "HQC-5" "FrodoKEM-976-AES" "FrodoKEM-1344-AES" "Classic-McEliece-" "Classic-McEliece-")
plugin_config_path="src/plugins/plugin-config/liboqs-any-aes256.yaml"
kem_rounds=$1 #10

for kem in ${kems[@]}; do
    i=0
    echo "liboqs_alg_name: $kem" > $plugin_config_path  # Write KEM name to plugin config
    while [ $i -lt $kem_rounds ]; do
        docker compose up  # run program
        ((i++))
    done
done