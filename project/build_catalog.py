"""Verify independent demo assets. No history lookup, conversion, models or network."""
import argparse
from server import load_catalog

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets-dir')
    args = parser.parse_args()
    try:
        catalog = load_catalog(args.assets_dir)
    except (ValueError, OSError) as error:
        parser.exit(2, str(error) + '\n')
    print(f"Verified {len(catalog['samples'])} samples / {sum(len(s['results']) for s in catalog['samples'])} results / {len(catalog['assets'])} images + provenance. No HDR needed.")
