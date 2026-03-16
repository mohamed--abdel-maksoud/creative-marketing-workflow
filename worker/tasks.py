from celery_app import app
import requests
import re
import os
import tempfile
import io
from PIL import Image
import json
import datetime
from typing import Dict, Any, Optional, List
import agents
import generate


try:
    from google import genai
    from google.genai import types

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None
    types = None


is_test_run_ = False  # if true, caches llm calls while testing


def verify_aspect_ratio(image_bytes: bytes, expected_ratio: str) -> bool:
    """
    Verify that the image's aspect ratio matches the expected ratio (e.g., '16:9').
    Returns True if matches within tolerance.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        if height == 0:
            return False
        actual = width / height
        # Parse expected ratio
        if ':' in expected_ratio:
            num, denom = expected_ratio.split(':')
            target = int(num) / int(denom)
        else:
            # Assume decimal
            target = float(expected_ratio)
        tolerance = 0.05
        return abs(actual - target) <= tolerance
    except Exception:
        return False


def extract_prompts_from_result(result: str) -> list[dict]:
    with open('tests/data/crew-answer.txt', 'w+') as f:
        f.write(result.raw)

    lines = [line.strip() for line in result.raw.splitlines()]
    prompts = []
    for line in lines:
        # example: A close-up shot of ... on the mug. //ratio=1:1;product=Fresh Morning Coffee;variation=1
        parts = line.split('//')
        if len(parts) != 2:
            raise ValueError(f'Invalid prompt format returned by Crew: {line}')
        [text, params] = parts
        m = re.match(r'^ratio=(.+);product=(.+);variation=(.+);lang=(.+)$', params)
        if m is None:
            raise ValueError(f'Invalid prompt format (params) returned by Crew: {line}')
        prompts.append(
            {
                'text': text,
                'ratio': m.group(1),
                'product': m.group(2),
                'variation': m.group(3),
                'lang': m.group(4),
            }
        )

    return prompts


CMS_URL = os.environ.get('CMS_URL', 'http://cms:8055')
CMS_API_KEY = os.environ.get('CMS_API_KEY', 'admin-key')


def get_campaign(campaign_id: str) -> Dict[str, Any]:
    headers = {'Authorization': f'Bearer {CMS_API_KEY}'}
    fields = [
        'id',
        'name', 'status',
        'target_audience',
        'target_languages',
        'message',
        'input_assets.*.id',
        'products.*.id',
        'products.*.name',
        'products.*.color_palette',
        'products.*.logo.id',
    ]
    resp = requests.get(
        f'{CMS_URL}/items/campaign/{campaign_id}?fields=' + ','.join(fields),
        headers=headers,
    )
    resp.raise_for_status()
    campaign = resp.json()['data']

    with open('tests/data/current-campaign.json', 'w+') as f:
        json.dump(campaign, f, indent='\t')

    return campaign


def download_asset(asset_id: str) -> bytes:
    """
    Download asset file from CMS.
    """
    headers = {'Authorization': f'Bearer {CMS_API_KEY}'}
    resp = requests.get(f'{CMS_URL}/assets/{asset_id}', headers=headers)
    resp.raise_for_status()
    return resp.content


def download_campaign_assets(campaign: Dict[str, Any]) -> Dict[str, bytes]:
    """
    Download all assets referenced by the campaign: input assets and product logos.
    Optionally saves assets in a temporary directory with campaign-id prefix.
    Returns dict mapping asset_id to bytes.
    """
    campaign_id = campaign.get('id', 'unknown')
    save_assets = os.environ.get('SAVE_ASSETS', '').lower() in ('1', 'true', 'yes')
    tmp_dir = None
    if save_assets:
        tmp_dir = os.path.join(
            tempfile.gettempdir(), f'creative-automation-{campaign_id}'
        )
        os.makedirs(tmp_dir, exist_ok=True)
        print(f'Saving downloaded assets to {tmp_dir}')

    assets = {}
    # Download input assets
    for asset in campaign.get('input_assets', []):
        file_id = asset.get('directus_files_id', {}).get('id')
        if file_id:
            try:
                asset_bytes = download_asset(file_id)
                assets[file_id] = asset_bytes
                if tmp_dir:
                    file_path = os.path.join(tmp_dir, f'{file_id}.bin')
                    with open(file_path, 'wb') as f:
                        f.write(asset_bytes)
            except Exception as e:
                print(f'Failed to download input asset {file_id}: {e}')
    # Download product logos
    for product in campaign.get('products', []):
        logo_id = product.get('product_id', {}).get('logo', {}).get('id')
        if logo_id:
            try:
                logo_bytes = download_asset(logo_id)
                assets[logo_id] = logo_bytes
                if tmp_dir:
                    file_path = os.path.join(tmp_dir, f'{logo_id}.bin')
                    with open(file_path, 'wb') as f:
                        f.write(logo_bytes)
            except Exception as e:
                print(f'Failed to download logo {logo_id}: {e}')
    return assets


def generate_missing_input_assets(
    campaign: Dict[str, Any], downloaded_assets: Optional[Dict[str, bytes]] = None
) -> None:
    """
    Ensure there is at least one input asset for each aspect ratio (1:1, 16:9, 9:16).
    If some assets are present, generate missing aspect ratios using generic prompts.
    """
    input_assets = campaign.get('input_assets', [])
    if not input_assets:
        # No input assets at all, generate all three ratios
        campaign_id = campaign['id']
        aspect_ratios = ['1:1', '16:9', '9:16']
        for ratio in aspect_ratios:
            prompt = f"Creative marketing background for campaign about {campaign['message']}, aspect ratio {ratio}, vibrant colors, abstract design, professional"
            try:
                image_bytes = generate.generate_image(prompt, ratio)
                if image_bytes:
                    if downloaded_assets is not None:
                        downloaded_assets[f'generated_input_{ratio}'] = image_bytes
                    filename = f'{campaign_id}_input_{ratio}.png'
                    file_id = upload_file(image_bytes, filename)
                    upload_asset(
                        campaign_id,
                        file_id,
                        ['generated', 'input-asset'],
                        {'prompt': prompt, 'ratio': ratio},
                    )
                    print(f'Generated input asset for ratio {ratio}')
            except Exception as e:
                print(f'Failed to generate input asset for ratio {ratio}: {e}')
        return

    # Some input assets exist: determine which aspect ratios are covered
    standard_ratios = {'1:1': 1.0, '16:9': 16 / 9, '9:16': 9 / 16}
    tolerance = 0.05
    covered_ratios = set()

    asset0_bytes = None
    for asset in input_assets:
        file_id = asset.get('directus_files_id', {}).get('id')
        if not file_id:
            continue
        # Get image bytes
        image_bytes = None
        if downloaded_assets and file_id in downloaded_assets:
            image_bytes = downloaded_assets[file_id]
        else:
            # Download if not already available
            try:
                image_bytes = download_asset(file_id)
            except Exception as e:
                print(
                    f'Failed to download asset {file_id} for aspect ratio detection: {e}'
                )
                continue
        if not image_bytes:
            continue

        if asset0_bytes is None:
            asset0_bytes = image_bytes
        # Compute aspect ratio
        try:
            img = Image.open(io.BytesIO(image_bytes))
            width, height = img.size
            if height == 0:
                continue
            aspect = width / height
            # Match to standard ratio
            for ratio_name, target in standard_ratios.items():
                if abs(aspect - target) <= tolerance:
                    covered_ratios.add(ratio_name)
                    break
        except Exception as e:
            print(f'Failed to process image {file_id}: {e}')

    # Generate missing ratios
    missing_ratios = [r for r in standard_ratios.keys() if r not in covered_ratios]
    if not missing_ratios:
        print('All standard aspect ratios already covered by input assets')
        return

    campaign_id = campaign['id']
    for ratio in missing_ratios:
        prompt = f"Creative marketing background for campaign about {campaign['message']}, aspect ratio {ratio}, vibrant colors, abstract design, professional"
        try:
            if asset0_bytes is None:
                image_bytes = generate.generate_image(prompt, ratio)
            else:
                image_bytes = generate.generate_image(
                    prompt, ratio, {'reference.png': asset0_bytes}
                )
            if image_bytes:
                if downloaded_assets is not None:
                    downloaded_assets[f'generated_input_{ratio}'] = image_bytes
                filename = f'{campaign_id}_input_{ratio}.png'
                file_id = upload_file(image_bytes, filename)
                upload_asset(
                    campaign_id,
                    file_id,
                    ['generated', 'input-asset'],
                    {'prompt': prompt, 'ratio': ratio},
                )
                print(f'Generated missing input asset for ratio {ratio}')
        except Exception as e:
            print(f'Failed to generate missing input asset for ratio {ratio}: {e}')


def upload_asset(
    campaign_id: str,
    file_url: str,
    tags: list,
    params: dict,
    product_id: Optional[str] = None,
):
    headers = {'Authorization': f'Bearer {CMS_API_KEY}'}
    payload = {
        'file': file_url,
        'tags': tags,
        'creation_parameters': params,
        'campaign': campaign_id,
    }
    if product_id is not None:
        payload['product'] = product_id
    resp = requests.post(f'{CMS_URL}/items/asset', headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()['data']


def update_campaign_status(campaign_id: str, status: str):
    headers = {'Authorization': f'Bearer {CMS_API_KEY}'}
    payload = {'status': status}
    resp = requests.patch(
        f'{CMS_URL}/items/campaign/{campaign_id}', headers=headers, json=payload
    )
    resp.raise_for_status()


def upload_file(file_bytes: bytes, filename: str) -> str:
    headers = {'Authorization': f'Bearer {CMS_API_KEY}'}
    files = {'file': (filename, file_bytes, 'image/png')}
    resp = requests.post(f'{CMS_URL}/files', headers=headers, files=files)
    resp.raise_for_status()
    return resp.json()['data']['id']


def save_assets_locally(
    campaign: Dict[str, Any],
    assets: Dict[str, bytes],
    product_by_id: Dict[str, Dict],
    generated_images: List[Dict[str, Any]],
) -> None:
    """
    Save input assets, logos, and generated output assets to a local folder.

    Directory structure:
        <SAVE_ASSETS_DIR>/<campaign name>/<run-timestamp>/
            input-assets/
                <asset_id>.png (or .bin)
                ...
            <product name>/
                <campaign_id>_<product_id>_<lang>_<ratio>_<variation>.png
                ...

    If SAVE_ASSETS_DIR environment variable is not set, defaults to './creations'.
    """
    save_dir = os.environ.get('SAVE_ASSETS_DIR', './output')
    campaign_name = campaign.get('name', 'unknown_campaign').replace('/', '_')
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    parent_dir = os.path.join(save_dir, campaign_name, timestamp)
    os.makedirs(parent_dir, exist_ok=True)

    # Save input assets and logos
    input_assets_dir = os.path.join(parent_dir, 'input-assets')
    os.makedirs(input_assets_dir, exist_ok=True)
    for asset_id, asset_bytes in assets.items():
        # Determine file extension based on content or assume .png
        try:
            _ = Image.open(io.BytesIO(asset_bytes))
            ext = '.png'
        except Exception:
            ext = '.bin'
        filename = f'{asset_id}{ext}'
        filepath = os.path.join(input_assets_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(asset_bytes)

    # Save generated images per product
    for img_info in generated_images:
        product_id = img_info['product_id']
        product = product_by_id.get(product_id, {})
        product_name = product.get('name', product_id).replace('/', '_')
        product_dir = os.path.join(parent_dir, product_name)
        os.makedirs(product_dir, exist_ok=True)
        filename = img_info['filename']
        filepath = os.path.join(product_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(img_info['bytes'])

    print(f'Assets saved locally to {parent_dir}')


def check_image_quality(
    image_bytes: bytes, logo_bytes: bytes, color_palette: str
) -> list[str]:
    """
    Use Gemini multimodal API to check if logo is present and color palette respected.
    Returns a list of tags indicating issues found.
    Possible tags: missing_logo, wrong_palette, quality_check_failed.
    """
    if not GEMINI_AVAILABLE:
        print('Gemini API not available, skipping quality check')
        return ['quality_check_skipped']
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    if not GEMINI_API_KEY:
        print('GEMINI_API_KEY not set, skipping quality check')
        return ['quality_check_skipped']
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""
    Analyze this image and answer the following questions:
    1. Is the logo present and clearly visible? The logo is provided as a reference image.
    2. Does the color palette match the following description: {color_palette}
    Answer with "YES" or "NO" for each question on a separate line.
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(data=logo_bytes, mime_type='image/png'),
                types.Part.from_bytes(data=image_bytes, mime_type='image/png'),
                prompt,
            ],
        )
        text = response.text.strip().upper()
        lines = [line.strip() for line in text.split('\n')]
        tags = []
        # Expecting two lines with YES/NO
        if len(lines) >= 2:
            if not lines[0].startswith('YES'):
                tags.append('missing_logo')
            if not lines[1].startswith('YES'):
                tags.append('wrong_palette')
        else:
            print(f'Unexpected response format: {text}')
            tags.append('quality_check_failed')
        return tags
    except Exception as e:
        print(f'Quality check failed: {e}')
        return ['quality_check_failed']


@app.task(name='process_campaign')
def process_campaign(campaign_id: str):
    try:
        campaign = get_campaign(campaign_id)
        if campaign['status'] != 'ready':
            print(f'campaign {campaign["id"]} not ready ({campaign["status"]}), skipping')
            return

        process_campaign_data(campaign)
    except Exception as e:
        update_campaign_status(campaign_id, 'failed')
        print(f'Error processing campaign {campaign_id}: {e}')
        raise


def process_campaign_data(campaign):
    campaign_id = campaign['id']
    update_campaign_status(campaign_id, 'processing')

    print('Step 1: Downloading assets...')
    assets = download_campaign_assets(campaign)

    generate_missing_input_assets(campaign, assets)
    # product id to product props
    product_by_id = {}
    target_languages = campaign['target_languages']
    products = campaign['products']
    for product in products:
        name = product['product_id']['name']
        pid = product['product_id']['id']
        logo_id = product['product_id']['logo']['id']
        color_palette = product['product_id']['color_palette']
        product_by_id[pid] = {
            'name': name,
            'id': pid,
            'logo': download_asset(logo_id),
            'color_palette': color_palette,
        }
    print(
        f'Downloaded {len(assets)} assets, found logos for {len(product_by_id)} products'
    )

    print('Step 2: Starting crew agents...')

    if is_test_run_:
        with open('tests/data/crew-answer1.txt') as f:
            t = f.read()
            from collections import namedtuple

            result = namedtuple('CrewResult', 'raw')
            result.raw = t
    else:
        crew = agents.create_campaign_crew(campaign)
        result = crew.kickoff()

    prompts = extract_prompts_from_result(result)
    print(f'Generated {len(prompts)} prompts')

    aspect_ratios = ['1:1', '16:9', '9:16']

    total_needed = len(products) * len(target_languages) * len(aspect_ratios) * 3

    if len(prompts) < total_needed:
        raise ValueError(
            f'The agent crew generated {len(prompts)}, expected {total_needed}. Review the workflow'
        )

    print('Step 3: Generating images & checking quality')
    generated_images = []  # list of dicts with product_id, filename, bytes
    for prompt in prompts:
        product = product_by_id[prompt['product']]
        product_id = product['id']
        logo_bytes = product['logo']
        color_palette = product['color_palette']
        ratio = prompt['ratio']
        lang = prompt['lang']
        variation = prompt['variation']
        ###
        image_bytes = generate.generate_image(
            prompt['text'], ratio, {
                'logo.png': logo_bytes,
                **{f'{k}.png': v for k, v in assets.items()},
            },
        )
        if not image_bytes:
            print(
                f"Image generation failed for prompt {json.dumps(prompt, indent='  ')}, skipping"
            )
            continue

        tags = []
        # Verify aspect ratio
        if not verify_aspect_ratio(image_bytes, ratio):
            tags.append('wrong_aspect_ratio')

        # Quality check if logo exists
        if logo_bytes and color_palette:
            quality_tags = check_image_quality(image_bytes, logo_bytes, color_palette)
            if not quality_tags:
                tags.append('quality-passed')
            else:
                tags.append('quality-failed')
                tags.extend(quality_tags)
        else:
            tags.append('quality-skipped')


        filename = f'{campaign_id}_{product_id}_{lang}_{ratio}_{variation}.png'
        generated_images.append(
            {
                'product_id': product_id,
                'filename': filename,
                'bytes': image_bytes,
            }
        )
        file_id = upload_file(image_bytes, filename)
        upload_asset(
            campaign_id,
            file_id,
            tags,
            {'prompt': prompt, 'ratio': ratio},
            product_id=product_id,
        )

        if is_test_run_:
            break

    # Save assets locally
    save_assets_locally(campaign, assets, product_by_id, generated_images)

    update_campaign_status(campaign_id, 'processed')
    print(f'Campaign {campaign_id} processed')


if __name__ == '__main__':
    # quick test
    campaign = get_campaign('024b7261-014d-4310-a2ba-76e0df333b79')
    # with open("tests/data/campaign1.json") as f:
    # campaign = json.load(f)
    process_campaign_data(campaign)
