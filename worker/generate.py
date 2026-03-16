import os
import base64
import logging
import replicate

logger = logging.getLogger(__name__)

REPLICATE_API_TOKEN = os.environ.get('REPLICATE_API_TOKEN')
FLUX_MODEL = os.environ.get('FLUX_MODEL', 'black-forest-labs/flux-2-pro')

SUPPORTED_RATIOS = {'1:1', '16:9', '9:16', '4:3', '3:4', '2:3', '3:2', '1:2', '2:1'}

_MODEL_MAX_REFS = {
    'black-forest-labs/flux-2-pro': 8,
    'black-forest-labs/flux-2-flex': 10,
    'black-forest-labs/flux-2-dev': 8,
}


def _mime_type(name: str) -> str:
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    return {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'webp': 'image/webp'}.get(
        ext, 'image/png'
    )


def _to_data_uri(name: str, data: bytes) -> str:
    mime = _mime_type(name)
    b64 = base64.b64encode(data).decode('utf-8')
    return f'data:{mime};base64,{b64}'


def generate_image_(
    prompt: str,
    aspect_ratio: str,
    reference_images: dict[str, bytes] | None = None,
) -> bytes:
    """
    Generate an image using FLUX.2 via Replicate.

    If reference_images is provided (name -> bytes, order matters), images are
    passed as the input_images array. The prompt is augmented with an ordered
    description so the model knows what each image is
    (e.g. "image 1 (logo.png), image 2 (background.jpg)").

    Returns PNG bytes.
    """
    if not REPLICATE_API_TOKEN:
        raise ValueError('REPLICATE_API_TOKEN environment variable not set')

    client = replicate.Client(api_token=REPLICATE_API_TOKEN)

    ratio = aspect_ratio if aspect_ratio in SUPPORTED_RATIOS else '1:1'
    max_refs = _MODEL_MAX_REFS.get(FLUX_MODEL, 8)

    input_params: dict = {
        'aspect_ratio': ratio,
        'output_format': 'png',
        'output_quality': 95,
        'seed': 1024,
    }

    if reference_images:
        if len(reference_images) > max_refs:
            raise ValueError(
                f'{FLUX_MODEL} supports up to {max_refs} reference images, '
                f'got {len(reference_images)}'
            )

        image_descriptions = ', '.join(
            f'image {i + 1} ({name})' for i, name in enumerate(reference_images)
        )
        input_params[
            'prompt'
        ] = f'{prompt}. Reference images in order: {image_descriptions}.'

        # Single array — new schema replaces the old numbered input_image_N keys
        input_params['input_images'] = [
            _to_data_uri(name, data) for name, data in reference_images.items()
        ]
        logger.debug(
            f'Sending {len(reference_images)} reference image(s) as input_images array'
        )
    else:
        input_params['prompt'] = prompt

    try:
        output = client.run(FLUX_MODEL, input=input_params)

        if not output:
            raise RuntimeError('No output returned from Replicate')

        file_output = output[0] if isinstance(output, list) else output
        return file_output.read()

    except replicate.exceptions.ModelError as e:
        logger.error(f'Replicate model error: {e}')
        raise
    except Exception as e:
        logger.error(f'Image generation failed: {e}')
        raise

def generate_image(
    prompt: str,
    aspect_ratio: str,
    reference_images: dict[str, bytes] | None = None,
) -> bytes:
    # TODO cache results by parameters
    last_e = None
    for _ in range(3):
        try:
            return generate_image_(prompt, aspect_ratio, reference_images)
        except Exception as e:
            last_e = e

    logger.error(f'Image generation failed all retries: {last_e}')
    raise last_e

