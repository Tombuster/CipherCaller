#!/bin/bash

kems=("ML-KEM-512" "ML-KEM-768" "ML-KEM-1024" "HQC-1" "HQC-3" "HQC-5" "FrodoKEM-976-AES" "FrodoKEM-1344-AES" "Classic-McEliece-" "Classic-McEliece-")
plugin_config_path="src/plugins/plugin-config/liboqs-any-aes256.yaml"
kem_rounds=10
i=0

for kem in ${kems[@]}; do
    # Write kem name to plugin config
    echo "liboqs_alg_name: $kem" > $plugin_config_path
    while [ $i -le $kem_rounds ]; do
        # Run the measurement
        ((i++))
    done
done