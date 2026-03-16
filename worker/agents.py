from crewai import Agent, Task, Crew
from langchain_google_genai import ChatGoogleGenerativeAI
import os
import prompts

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

llm = ChatGoogleGenerativeAI(model='gemini-2.5-flash', google_api_key=GEMINI_API_KEY)


def create_prompting_wizard():
    return Agent(
        role='Prompting Wizard',
        goal='Generate high-quality image prompts for Flux 2.0 using best practices',
        backstory=prompts.get_prompting_wizard_instructions(),
        llm=llm,
        verbose=True,
        allow_delegation=True,
    )


def create_legal_expert():
    return Agent(
        role='Legal Expert',
        goal='Review image prompts for compliance with regional advertising laws and regulations',
        backstory=prompts.get_legal_expert_instructions(),
        llm=llm,
        verbose=True,
        allow_delegation=True,
    )


def create_quality_assurance():
    return Agent(
        role='Quality Assurance',
        goal='Review image prompts for brand consistency, logo placement, color scheme, and overall effectiveness',
        backstory=prompts.get_quality_assurance_instructions(),
        llm=llm,
        verbose=True,
        allow_delegation=True,
    )


def create_campaign_crew(campaign_data):
    prompting = create_prompting_wizard()
    legal = create_legal_expert()
    qa = create_quality_assurance()

    # Define tasks based on campaign data
    n_variations = 3
    # n_variations = 1 # debug
    products = campaign_data.get('products', [])
    target_languages = campaign_data.get('target_languages', [])
    aspect_ratios = ['1:1', '16:9', '9:16']
    nprompts = len(products) * len(target_languages) * len(aspect_ratios) * n_variations

    prompt_task = Task(
        description=f"""
        Generate high-quality image prompts for Flux 2.0 image generation model.
        
        Campaign message: {campaign_data['message']}
        Target languages: {target_languages}
        Products: {products}
        Aspect ratios: {aspect_ratios}
        
        You need to create {n_variations} variations per product, per language, per aspect ratio.
        That's total {nprompts} prompts.
        Make sure to translate the campaign message in the prompt's language consistently. E.g. two prompts in French with different aspect ratios should have the message translated the same way.
        Make sure to add explicit instructions to include the campaign message in the image.
        Make sure to add explicit instructions to use the logo (sent along with the prompt) in the image.
        Make sure to include the varation number in the prompt.
        
        Follow Flux prompting best practices:

            - Use natural language, not keyword list. Structure prompts with **subject first, then action, environment, lighting, and style.
            - use positive, descriptive language to guide the model toward sharp details and accurate anatomy .
            - Add photographic terminology for realism. Include specific camera specs (e.g., "85mm lens, f/1.8"), lighting descriptions, and texture cues (e.g., "natural skin texture"). For text rendering, always put desired words in quotation marks.
            - Specify desired colors in hex code rather than words when possible.
        Output the prompts as plain text, one prompt per line. That's total {nprompts} lines.
        At the end of the prompt, write a suffix as follows: two slashes followed by ratio=<aspect-ratio>;product=<product id>;variation=<variation>;lang=<language>. example: `... //ratio=1:1;product=1f234-2399a-a234f-f008;variation=3;lang=en`
        """,
        agent=prompting,
        expected_output='Plain text, one prompt per line',
    )

    legal_review = Task(
        description=f"""
        Review the generated prompts for legal compliance in region: {campaign_data.get('target_region', 'global')}.
        
        Check for:
        - Copyright and trademark infringement
        - Privacy and data protection issues
        - Consumer protection and advertising standards
        - Cultural sensitivities and appropriateness
        - Restricted content (alcohol, tobacco, gambling)
        
        Output approved prompts as plain text, one prompt per line (modified if needed).
        """,
        agent=legal,
        expected_output='Plain text, one prompt per line',
    )

    qa_task = Task(
        description=f"""
        Review the approved prompts for brand consistency and quality.
        
        Check for:
        - The campaign message is translated in the prompt's language consistently.
          E.g. two prompts in French with different aspect ratios should have the message translated the same way.
        - There is a clear instruction to include the campaign message (or its translation) in the image
        - Color scheme alignment with brand guidelines
        - Messaging clarity and alignment with campaign objectives
        - Visual style consistency across variations
        - Overall appeal and effectiveness for target audience
        
        Output only the final prompts as plain text, one prompt per line. That's total {nprompts} lines.
        """,
        agent=qa,
        expected_output='Plain text, one prompt per line',
    )

    crew = Crew(
        agents=[prompting, legal, qa],
        tasks=[prompt_task, legal_review, qa_task],
        verbose=True,
        # tracing=True,
    )
    return crew
