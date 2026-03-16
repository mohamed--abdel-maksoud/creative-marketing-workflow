# Creative Automation Pipeline

This is a pipeline to create marketing campaign assets using AI agents and image generation models.


## How to Use

The system is completely managed by a CMS (Directus). The general workflow is:

1. log in to the CMS
2. create/edit a campaign
3. to execute the campaign, set the campaign status to `ready`
4. background tasks start and process the campaign. When the execution is
  completed, the campaign status is marked as either `processed` or `failed`
5. The campaign assets can be viewed in the CMS (assets collection)
  or in a folder in [the worker subdirectory](./worker/output).


### Running on a local machine

Before executing any command, you need to have API keys for Google's Gemini service and Replicate image generation service. Please update [.env.local](./.env.local) with these keys (and never commit them to git).

The local workflow is based on Docker (with the Compose plugin).
You also need to bootstrap the CMS once using the provided data in this repo (compressed with tar and gzip).
Once you have these installed, run this in the root of this repo:

```bash
# do this only once to bootstrap the CMS
tar xzf tests/data/cms-data.tar.gz

docker compose build
docker compose up -d
```

This starts the CMS on http://localhost:8055 .
The local login credentials are located in [compose.yml](./compose.yml), most likely `admin@example.com/admin123`.
Create and edit the campaign data in the CMS and check [the worker subdirectory](./worker/output) for campaign outputs.
You can see the logs of any of the components using:

```bash
docker compose logs -f worker  # backend, or cms
```


## Example input and output

The CMS (once bootstrapped) will have a campaign ready to edit.
The underlying data are in the [worker/tests/data/](./worker/tests/data/).
One output example is in the [worker/output/Campaign-FR-Q1 directory](./worker/output/Campaign-FR-Q1/).


## Architecture & Design Choices

- Use Directus CMS to define the data model and maintain campaign data.
  reasoning:
  - Ready UI to create/edit/view data
  - Built-in versioning of all entities
- Use a queue (Celery backed by Redis) to schedule campaign execution.
- Trigger queue insert in a CMS webhook on Campaign create/update.
  Use a dedicated backend to handle this logic.
- CrewAI for agent orchestration:
  - 3 agents: prompting wizard, legal expert, and quality-assurance agent.
  - built-in RAG and collaboration
  - limit the focus of each client.
- Flux (via Replicate API) for image generation.
  - good model, good with typography, supports multiple reference images
  - relatively cheap with accessible API


## Limitations & Roadmap

- save to S3
- fix message translation prompt
- implement a queue to make image generation more robust (retries, back-off)
- generally optimize prompts for the user's use case
- implement automated tests (at least in worker)
- specify production deployment
