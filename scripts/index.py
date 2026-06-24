import os, re, time, argparse, requests
import support

from elasticsearch import Elasticsearch
from datetime import datetime, timezone

utils_packs = {
    'mikroe_utils_common.7z': 'MikroE common utilities',
    'preinit.7z': 'Preinit library',
    'unit_test_lib.7z': 'Unit test library'
}

def increase_patch_version(version):
    parts = version.split(".")

    if len(parts) != 3:
        raise ValueError(f"Invalid version format: {version}")

    parts[2] = str(int(parts[2]) + 1)

    return ".".join(parts)


# Function to index release details into Elasticsearch
def index_release_to_elasticsearch(es, token, assets, index_names):
    # Get all indexes to go through all of them recursively
    # index_names = [
    #     os.environ['ES_INDEX_LIVE'],
    #     os.environ['ES_INDEX_TEST'],
    #     os.environ['ES_INDEX_EXPERIMENTAL']
    # ]

    necto_versions = {
        os.environ['ES_INDEX_LIVE'] : 'live',
        os.environ['ES_INDEX_TEST'] : 'dev',
        os.environ['ES_INDEX_EXPERIMENTAL'] : 'experimental'
    }

    indexing_mapping = {
        os.environ['ES_INDEX_LIVE'] : {},
        os.environ['ES_INDEX_TEST'] : {},
        os.environ['ES_INDEX_EXPERIMENTAL'] : {}
    }

    # Get the current time in UTC
    current_time = datetime.now(timezone.utc).replace(microsecond=0)
    # If you specifically want the 'Z' at the end instead of the offset
    published_at = current_time.isoformat().replace('+00:00', 'Z')

    # Fetch metadata contents
    metadata = support.fetch_release_metadata(assets, token)

    # Let's map all the items that we need to index with the index name
    for index_name in index_names:
        # Get all currently indexed items for this index
        indexed_items = support.fetch_current_indexed_packages(es, index_name)

        # Get all released assets for this index
        for asset in assets:
            doc = None
            indexed_item = None
            kibana_id = None

            # Database asset handling
            if f'database_{necto_versions[index_name]}.7z' == asset['name']:
                kibana_id = asset['name'].replace('.7z', '')
                doc = {
                    "name": "database",
                    "display_name": "NECTO Database",
                    "author": "MIKROE",
                    "hidden": True,
                    "version": "3.0.0",
                    "type": "database",
                    "created_at": asset['created_at'],
                    "updated_at": asset['updated_at'],
                    "published_at": published_at,
                    "hash": metadata[asset['name']]['hash'],
                    "category": "utility",
                    "download_link": asset['browser_download_url'],
                    "download_link_api": asset['url'],
                    "package_changed": True,
                    "install_location": "%APPLICATION_DATA_DIR%/databases",
                    "gh_package_name": asset['name'],
                    "_type": "_doc",
                    "dependencies": [
                        "mikroe_utils_common"
                    ]
                }
                indexed_item = support.find_asset(indexed_items, 'database')
                if indexed_item:
                    if doc['hash'] != indexed_item['hash']:
                        doc['version'] = increase_patch_version(indexed_item['version'])
                        indexing_mapping[index_name][kibana_id] = doc
                else:
                    indexing_mapping[index_name][kibana_id] = doc

            # Images asset handling
            elif 'images.7z' == asset['name']:
                kibana_id = 'images'
                doc = {
                    "name": "images",
                    "display_name": "NECTO Resources - Images",
                    "author": "MIKROE",
                    "hidden": True,
                    "version": "v3.0.0",
                    "type": "images",
                    "created_at": asset['created_at'],
                    "updated_at": asset['updated_at'],
                    "published_at": published_at,
                    "hash": metadata[asset['name']]['hash'],
                    "category": "resources",
                    "download_link": asset['browser_download_url'],
                    "download_link_api": asset['url'],
                    "package_changed": True,
                    "install_location": "%APPLICATION_DATA_DIR%/resources/images",
                    "gh_package_name": asset['name'],
                    "_type": "_doc"
                }
                indexed_item = support.find_asset(indexed_items, 'images')
                if indexed_item:
                    if doc['hash'] != indexed_item['hash']:
                        doc['version'] = increase_patch_version(indexed_item['version'])
                        indexing_mapping[index_name][kibana_id] = doc
                else:
                    indexing_mapping[index_name][kibana_id] = doc

            # LVGL package handling
            elif asset['name'].startswith('lvgl_') and f'_{necto_versions[index_name]}.7z' in asset['name']:
                kibana_id = asset['name'].replace(f'{necto_versions[index_name]}.7z', '')
                doc = {
                    "name": kibana_id,
                    "display_name": metadata[asset['name']]['display_name'],
                    "hidden": False,
                    "vendor": "MIKROE",
                    "version": "3.0.0",
                    "type": "legacy_sdk",
                    "created_at": asset['created_at'],
                    "updated_at": asset['updated_at'],
                    "published_at": published_at,
                    "hash": metadata[asset['name']]['hash'],
                    "category": "SDK Library",
                    "download_link": asset['browser_download_url'],
                    "download_link_api": asset['url'],
                    "install_location": "%APPLICATION_DATA_DIR%/packages/lvgl",
                    "package_changed": True,
                    "gh_package_name": asset['name'],
                    "_type": "_doc"
                }
                indexed_item = support.find_asset(indexed_items, asset['name'].replace(f'_{necto_versions[index_name]}.7z', ''))
                if indexed_item:
                    if doc['hash'] != indexed_item['hash']:
                        doc['version'] = increase_patch_version(indexed_item['version'])
                        indexing_mapping[index_name][kibana_id] = doc
                else:
                    indexing_mapping[index_name][kibana_id] = doc

            # NECTO utils packages handling
            elif asset['name'] in utils_packs:
                kibana_id = asset['name'].replace('7z', '')
                doc = {
                    "name": kibana_id,
                    "display_name": utils_packs[asset['name']],
                    "author": "MIKROE",
                    "hidden": True,
                    "type": kibana_id,
                    "version": "3.0.0",
                    "created_at": asset['created_at'],
                    "updated_at": asset['updated_at'],
                    "published_at": published_at,
                    "hash": metadata[asset['name']]['hash'],
                    "category": "utility",
                    "download_link": asset['browser_download_url'],
                    "download_link_api": asset['url'],
                    "package_changed": True,
                    "install_location": "%APPLICATION_DATA_DIR%/cmake",
                    "gh_package_name": asset['name'],
                    "_type": "_doc"
                }
                indexed_item = support.find_asset(indexed_items, kibana_id)
                if indexed_item:
                    if doc['hash'] != indexed_item['hash']:
                        doc['version'] = increase_patch_version(indexed_item['version'])
                        indexing_mapping[index_name][kibana_id] = doc
                else:
                    indexing_mapping[index_name][kibana_id] = doc

            # NECTO translation packs handling
            elif 'necto-translations' in asset['name']:
                kibana_id = metadata[asset['name']]['name'].replace('-', '_')
                doc = {
                    "name": metadata[asset['name']]['name'],
                    "version": metadata[asset['name']]['version'],
                    "type": metadata[asset['name']]['type'],
                    "display_name": metadata[asset['name']]['display_name'],
                    "author": "MIKROE",
                    "short_description": metadata[asset['name']]['short_description'],
                    "hidden": False,
                    "created_at": asset['created_at'],
                    "updated_at": asset['updated_at'],
                    "published_at": published_at,
                    "hash": metadata[asset['name']]['hash'],
                    "download_link": asset['browser_download_url'],
                    "download_link_api": asset['url'],
                    "package_changed": True,
                    "install_location": f"%APPLICATION_DATA_DIR%/packages/translations/{metadata[asset['name']]['name']}",
                    "gh_package_name": asset['name'],
                    "_type": "_doc"
                }
                indexed_item = support.find_asset(indexed_items, kibana_id)
                if indexed_item:
                    if doc['hash'] != indexed_item['hash']:
                        indexing_mapping[index_name][kibana_id] = doc
                else:
                    indexing_mapping[index_name][kibana_id] = doc

            # NECTO tempaltes packs handling
            elif 'templates_' in asset['name']:
                # kibana_id = metadata[asset['name']]['name'].replace('-', '_')
                # doc = {
                #     "name": metadata[asset['name']]['name'],
                #     "version": metadata[asset['name']]['version'],
                #     "type": metadata[asset['name']]['type'],
                #     "display_name": metadata[asset['name']]['display_name'],
                #     "author": "MIKROE",
                #     "short_description": metadata[asset['name']]['short_description'],
                #     "hidden": False,
                #     "created_at": asset['created_at'],
                #     "updated_at": asset['updated_at'],
                #     "published_at": published_at,
                #     "hash": metadata[asset['name']]['hash'],
                #     "download_link": asset['browser_download_url'],
                #     "download_link_api": asset['url'],
                #     "package_changed": True,
                #     "install_location": f"%APPLICATION_DATA_DIR%/packages/translations/{metadata[asset['name']]['name']}",
                #     "gh_package_name": asset['name'],
                #     "_type": "_doc"
                # }
                # indexed_item = support.find_asset(indexed_items, kibana_id)
                # if indexed_item:
                #     if doc['hash'] != indexed_item['hash']:
                #         indexing_mapping[index_name][kibana_id] = doc
                # else:
                #     indexing_mapping[index_name][kibana_id] = doc



if __name__ == '__main__':
    # First, check for arguments passed
    def str2bool(v):
        if isinstance(v, bool):
            return v
        if v.lower() in ('yes', 'true', 't', 'y', '1'):
            return True
        elif v.lower() in ('no', 'false', 'f', 'n', '0'):
            return False
        else:
            raise argparse.ArgumentTypeError('Boolean value expected.')

    # Get arguments
    parser = argparse.ArgumentParser(description="Upload directories as release assets.")
    parser.add_argument("token", help="GitHub Token")
    parser.add_argument("repo", help="Repository name, e.g., 'username/repo'")
    parser.add_argument("index_names", help="Target index names")
    args = parser.parse_args()

    # Elasticsearch instance used for indexing
    num_of_retries = 1
    print("Trying to connect to ES.")
    while True:
        es = Elasticsearch([os.environ['ES_HOST']], http_auth=(os.environ['ES_USER'], os.environ['ES_PASSWORD']))
        if es.ping():
            break
        # Wait 1 second and try again if connection fails
        if 10 == num_of_retries:
            # Exit if it fails 10 times, something is wrong with the server
            raise ValueError("Connection to ES failed!")
        print(f"Connection retry: {num_of_retries}")
        num_of_retries += 1

        time.sleep(1)

    # Fetch current metadata contents
    latest_release = support.get_latest_release(args.repo, args.token)
    assets = support.get_release_assets(args.repo, latest_release['id'], args.token)

    # Now index the new release
    index_release_to_elasticsearch(
        es,
        args.token,
        assets,
        args.index_names
    )
