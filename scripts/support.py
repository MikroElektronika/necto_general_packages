import requests, io, py7zr

from elasticsearch import Elasticsearch

def github_headers(token, download=False):
    headers = {
        "Authorization": f"token {token}",
        "User-Agent": "NECTO-release-assets-script"
    }

    if download:
        headers["Accept"] = "application/octet-stream"

    return headers

def get_latest_release(repo, token):
    ''' Fetch the version that is labeled as "latest" '''
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    resp = requests.get(url, headers=github_headers(token), timeout=30)
    resp.raise_for_status()
    latest_release = resp.json()
    return latest_release

def extract_archive_from_url(url, destination, token=None, log_download_link=False):
    """
    Extract the contents of an archive (7z or zip) from a URL directly
    in memory, without downloading the file.
    """
    if log_download_link:
        print(f"Download link: {url}")
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/octet-stream'
    }
    if 'github' in url:
        response = requests.get(url, headers=headers, stream=True)
    else:
        response = requests.get(url, stream=True)

    response.raise_for_status()

    if response.status_code == 200: ## Response OK?
        with io.BytesIO() as byte_stream:

            for chunk in response.iter_content(chunk_size=8192):
                byte_stream.write(chunk)

            byte_stream.seek(0)

            with py7zr.SevenZipFile(byte_stream, mode='r') as archive:
                archive.extractall(path=destination)
    else:
        raise Exception(f"Failed to download file: status code {response.status_code}")

def get_release_assets(repo, release_id, token):
    assets = []
    page = 1

    while True:
        url = f"https://api.github.com/repos/{repo}/releases/{release_id}/assets?page={page}&per_page=100"
        response = requests.get(url, headers=github_headers(token))
        response.raise_for_status()

        page_assets = response.json()
        if not page_assets:
            break

        assets.extend(page_assets)
        page += 1

    return assets

def find_asset(assets, asset_name):
    for asset in assets:
        if asset["name"] == asset_name:
            return asset

    return None

def fetch_release_metadata(assets, token):
    metadata_asset = find_asset(assets, "metadata.json")
    if not metadata_asset:
        return None

    response = requests.get(metadata_asset["url"], headers=github_headers(token, download=True))
    response.raise_for_status()

    return response.json()

def delete_release_asset(asset, token):
    print(f"\033[93mDeleting existing asset: {asset['name']}\033[0m")

    response = requests.delete(asset["url"], headers=github_headers(token))
    response.raise_for_status()

    print(f"\033[91mDeleted asset: {asset['name']}\033[0m")

def upload_release_asset(repo, release_id, asset_path, token):
    asset_name = asset_path.name

    if asset_name.endswith(".zip"):
        content_type = "application/zip"
    elif asset_name.endswith(".7z"):
        content_type = "application/x-7z-compressed"
    elif asset_name.endswith(".json"):
        content_type = "application/json"
    else:
        content_type = "application/octet-stream"

    url = f"https://uploads.github.com/repos/{repo}/releases/{release_id}/assets?name={asset_name}"

    headers = github_headers(token)
    headers["Content-Type"] = content_type

    print(f"\033[94mUploading asset: {asset_name}\033[0m")

    with open(asset_path, "rb") as file:
        response = requests.post(url, headers=headers, data=file)

    response.raise_for_status()

    print(f"\033[92mUploaded asset: {asset_name}\033[0m")
    return response.json()

def fetch_current_indexed_packages(es : Elasticsearch, index_name):
    # Search query to use
    query_search = {
        "size": 5000,
        "query": {
            "match_all": {}
        }
    }

    # Search the base with provided query
    num_of_retries = 1
    while num_of_retries <= 10:
        try:
            response = es.search(index=index_name, body=query_search)
            if not response['timed_out']:
                break
        except:
            print("Executing search query - retry number %i" % num_of_retries)
        num_of_retries += 1

    all_packages = []
    for eachHit in response['hits']['hits']:
        if not 'name' in eachHit['_source']:
            continue
        if '_type' in eachHit:
            if '_doc' == eachHit['_type']:
                all_packages.append(eachHit['_source'])

    # Sort all_packages alphabetically by the 'name' field
    all_packages.sort(key=lambda x: x['name'])

    return all_packages
