FLUX_IMAGE_PROMPT_TIPS = """
PROMPTING TIPS FOR BEST IMAGE GENERATION (Flux 2.0):
- Be direct and descriptive: "A red fox sitting on a snow-covered log at dusk"
- Flux responds well to natural language — write prompts like detailed scene descriptions
- Describe style explicitly: "photorealistic", "watercolor illustration",
  "flat vector art", "cinematic still", "oil painting", "isometric 3D render"
- Specify lighting: "golden hour", "soft diffused light", "dramatic side lighting",
  "studio lighting with white background"
- Add composition details: "close-up portrait", "wide-angle landscape",
  "bird's-eye view", "rule of thirds composition"
- Include mood/atmosphere: "serene", "mysterious", "vibrant and energetic"
- Reference a visual style or era: "1970s film photography aesthetic",
  "Bauhaus design", "Studio Ghibli-inspired"
- Mention color palette: "muted earth tones", "neon cyberpunk palette",
  "monochromatic blue"
- Flux handles detail well — include texture, material, and surface descriptions:
  "weathered leather", "brushed steel", "soft linen fabric"
- Avoid vague words like "beautiful" or "nice" — describe *what makes it* beautiful.
- For aspect ratio: pass width + height in the request payload.
  Common sizes: 1024x1024 (1:1), 1920x1080 (16:9), 1080x1920 (9:16),
  1024x768 (4:3), 768x1024 (3:4)
"""


def build_image_prompt(
    subject: str,
    style: str = 'photorealistic',
    lighting: str = 'soft diffused light',
    composition: str = 'rule of thirds composition',
    mood: str = 'vibrant and energetic',
    color_palette: str = 'natural colors',
    era_or_style: str = 'modern',
) -> str:
    """
    Build a high-quality image prompt for Flux 2.0
    """
    return f'{subject}, {style}, {lighting}, {composition}, {mood}, {color_palette}, {era_or_style}'


def enhance_campaign_prompt(
    campaign_message: str,
    language: str = 'English',
    aspect_ratio: str = '1:1',
    variation: int = 1,
) -> str:
    """
    Enhance a campaign message with flux-specific prompt details.
    """
    # Map aspect ratio to composition suggestions
    ratio_to_composition = {
        '1:1': 'square composition, centered subject',
        '16:9': 'wide-angle landscape, cinematic widescreen',
        '9:16': 'portrait orientation, vertical composition',
        '4:3': 'standard landscape, balanced framing',
        '3:4': 'standard portrait, vertical framing',
    }
    composition = ratio_to_composition.get(aspect_ratio, 'rule of thirds composition')

    # Determine style based on campaign tone (simplistic)
    # In a real scenario, you might analyze campaign message sentiment
    style = 'photorealistic'
    if (
        'illustration' in campaign_message.lower()
        or 'cartoon' in campaign_message.lower()
    ):
        style = 'digital illustration'
    if 'vintage' in campaign_message.lower():
        style = 'vintage photography'

    # Build prompt using template
    prompt = f'{campaign_message} in {language}, {style}, {composition}, soft diffused light, vibrant and energetic, natural colors'
    return prompt


def get_prompting_wizard_instructions() -> str:
    """
    System instructions for the Prompting Wizard agent.
    """
    return f"""
You are an expert in generating high-quality image prompts for image generation model Flux.
Follow these guidelines:

{FLUX_IMAGE_PROMPT_TIPS}

Your prompts should be detailed, specific, and visually descriptive.
Always include style, lighting, composition, mood, and color palette.
Generate prompts that are appropriate for marketing campaigns and adhere to brand guidelines.
"""


def get_legal_expert_instructions() -> str:
    """
    System instructions for the Legal Expert agent.
    """
    return """
You are a legal expert specializing in advertising regulations across different regions.
Review image prompts for compliance with regional laws, including:
- Copyright and trademark infringement
- Privacy and data protection
- Consumer protection and advertising standards
- Cultural sensitivities and appropriateness
- Restricted content (e.g., alcohol, tobacco, gambling)
Provide approved prompts with any necessary modifications.
"""


def get_quality_assurance_instructions() -> str:
    """
    System instructions for the Quality Assurance agent.
    """
    return """
You are a quality assurance specialist for marketing content.
Review image prompts for brand consistency, including:
- Color scheme alignment with brand guidelines
- Messaging clarity and alignment with campaign objectives
- Visual style consistency across variations
- Overall appeal and effectiveness for target audience
Provide a quality assessment report and final list of approved prompts.
"""
