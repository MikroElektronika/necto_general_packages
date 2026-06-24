import os, time, argparse
import support

from elasticsearch import Elasticsearch
from datetime import datetime, timezone

def increase_patch_version(version):
    parts = version.split(".")

    if len(parts) != 3:
        raise ValueError(f"Invalid version format: {version}")

    parts[2] = str(int(parts[2]) + 1)

    return ".".join(parts)


# Function to index release details into Elasticsearch
def index_release_to_elasticsearch(es, token, assets, index_names):
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
            if 'metadata.json' == asset['name']:
                continue

            doc = None
            indexed_item = None
            kibana_id = None

            kibana_id = metadata[asset['name']]['name']
            doc = metadata[asset['name']]
            doc['created_at'] = asset['created_at']
            doc['updated_at'] = asset['updated_at']
            doc['published_at'] = published_at
            doc['download_link'] = asset['browser_download_url']
            doc['download_link_api'] = asset['url']
            doc['_type'] = '_doc'
            indexed_item = support.find_asset(indexed_items, kibana_id)
            if indexed_item:
                if doc['hash'] != indexed_item['hash']:
                    doc['version'] = increase_patch_version(indexed_item['version'])
                    indexing_mapping[index_name][kibana_id] = doc
            else:
                doc['version'] = '1.0.0'
                indexing_mapping[index_name][kibana_id] = doc


    # Let's update/create all the items that we need to index for requested indexes
    for index_name in index_names:
        # Get all currently indexed items for this index
        indexed_items = support.fetch_current_indexed_packages(es, index_name)

        for kibana_id, doc in indexing_mapping[index_name].items():
            indexed_item = support.find_asset(indexed_items, kibana_id)

            previous_version = None
            if indexed_item:
                previous_version = indexed_item['version']

            resp = es.index(index=index_name, doc_type=None, id=kibana_id, body=doc)
            print(f"{resp['result']} {resp['_id']}")

            # Print new version after indexing
            if previous_version != doc['version']:
                print(f"\033[95mVersion for asset {kibana_id} has been updated from {previous_version} to {doc['version']}\033[0m")


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
    parser.add_argument("index_names", help="Target index names divided by |")
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
        args.index_names.split('|')
    )
