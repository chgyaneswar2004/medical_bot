# Build-a-Complete-Medical-Chatbot-with-LLMs-LangChain-Pinecone-Flask-AWS

# How to run?
### STEPS:

Clone the repository

```bash
git clonehttps://github.com/entbappy/Build-a-Complete-Medical-Chatbot-with-LLMs-LangChain-Pinecone-Flask-AWS.git
```
### STEP 01- Create a conda environment after opening the repository

```bash
conda create -n medibot python=3.10 -y
```

```bash
conda activate medibot
```


### STEP 02- install the requirements
```bash
pip install -r requirements.txt
```


### Create a `.env` file in the root directory and add your Pinecone and Groq credentials as follows:

```ini
PINECONE_API_KEY="your-pinecone-key"
GROQ_API_KEY="your-groq-key"
```


```bash
# run the following command to store embeddings to pinecone
python store_index.py
```

```bash
# Finally run the following command
python app.py
```

Now,
```bash
open up http://127.0.0.1:8080
```


### Techstack Used:

- Python
- LangChain
- Flask
- GPT
- Pinecone



# Deploy to an AWS EC2 instance

The GitHub Actions workflow builds the Docker image, pushes it to ECR, then deploys it to an EC2-hosted self-hosted GitHub Actions runner.

1. Create an ECR repository and an Ubuntu EC2 instance in the same AWS region. Install Docker on the instance and configure the GitHub Actions self-hosted runner there. The runner user must be able to run Docker commands.
2. Attach an EC2 instance role that grants read access to the ECR repository (for example, `AmazonEC2ContainerRegistryReadOnly`). The GitHub Actions build job needs credentials with permission to push to that ECR repository; store them as GitHub Actions secrets.
3. In the EC2 security group, allow inbound TCP port 80 from the clients that should access the app. For a public demo, that can be `0.0.0.0/0`; for private use, restrict it to your IP or network.
4. Add these repository secrets in GitHub: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`, `ECR_REPO` (repository name only), `PINECONE_API_KEY`, and `GROQ_API_KEY`.
5. Push to the `main` branch. The workflow publishes the image and replaces the `medical-chatbot` container, serving it on port 80.

Do not commit `.env` or put API keys in the Docker image. The deployment passes the Pinecone and Groq keys to the running container as environment variables.
