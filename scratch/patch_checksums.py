import os
import hashlib

# Paths
truststore_path = r"c:\Users\gooro\OneDrive\Desktop\KisnardOnline\res\gamedata\truststore"
server_checksums_path = r"C:\Jay\WORKSPACE\JayServer\checksums.txt"
client_checksums_path = r"c:\Users\gooro\OneDrive\Desktop\KisnardOnline\checksums.txt"

def get_sha1(file_path):
    sha1 = hashlib.sha1()
    with open(file_path, 'rb') as f:
        while True:
            data = f.read(65536)
            if not data:
                break
            sha1.update(data)
    return sha1.hexdigest()

def patch_checksum_file(filepath, target_filename, new_hash):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return False
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    tokens = content.split('|')
    patched = False
    
    # B = string.split("|")
    # B[n] = path, B[n+1] = filename, B[n+2] = url, B[n+3] = checksum
    for i in range(0, len(tokens) - 3, 4):
        filename = tokens[i + 1]
        if filename == target_filename:
            old_hash = tokens[i + 3]
            tokens[i + 3] = new_hash
            print(f"Patched {target_filename} in {os.path.basename(filepath)}:")
            print(f"  Old Hash: {old_hash}")
            print(f"  New Hash: {new_hash}")
            patched = True
            break
            
    if patched:
        new_content = '|'.join(tokens)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return True
    else:
        print(f"Could not find {target_filename} in {filepath}")
        return False

if __name__ == "__main__":
    if not os.path.exists(truststore_path):
        print("Error: truststore file does not exist. Please run generate_pem.py first.")
        exit(1)
        
    # 1. Calculate SHA-1 of our custom truststore
    truststore_hash = get_sha1(truststore_path)
    print(f"Custom truststore SHA-1: {truststore_hash}")
    
    # 2. Patch both checksums.txt files
    patch_checksum_file(server_checksums_path, "truststore", truststore_hash)
    patch_checksum_file(client_checksums_path, "truststore", truststore_hash)
    
    print("Checksum patching complete!")
