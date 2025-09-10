# app.py (This will be the main file name for our script)

import os
import requests
import google.generativeai as genai
from datetime import datetime, timedelta

# --- Configuration (Get these from your environment variables later) ---
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Configure Google Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

def get_articles_from_newsapi(query="Canada AND clean energy", days_back=1, language="en"):
    """Fetches articles from News API for a given query."""
    if not NEWS_API_KEY:
        print("NEWS_API_KEY is not set.")
        return []

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)

    url = f"https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "language": language,
        "from": start_date.isoformat(),
        "to": end_date.isoformat(),
        "sortBy": "relevancy",
        "pageSize": 20, # Fetch up to 20 articles
        "apiKey": NEWS_API_KEY
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status() # Raise an exception for HTTP errors
        data = response.json()
        if data['status'] == 'ok':
            # Filter for reputable Canadian sources if possible, or just broader for PoC
            # For this PoC, we'll rely on the 'Canada' query and general relevance
            return data['articles']
        else:
            print(f"News API Error: {data.get('message', 'Unknown error')}")
            return []
    except requests.exceptions.RequestException as e:
        print(f"Error fetching news: {e}")
        return []

def analyze_and_summarize_with_gemini(articles):
    """Uses Gemini to analyze and summarize the articles."""
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY is not set.")
        return "Gemini API key is missing, cannot analyze news."

    if not articles:
        return "No articles found to analyze today. Try broadening your search!"

    # Construct the prompt with the persona and task
    persona_prompt = (
        "You are a senior political analyst specializing in Canadian politics, with a strong, "
        "skeptical focus on clean energy policy, innovation, and economic impact. "
        "You always look for concrete policy actions, investment trends, and potential "
        "challenges or 'greenwashing'. Your task is to analyze the following news articles "
        "from this perspective and provide a concise 'Morning Briefing'."
    )

    analysis_request_prompt = (
        "Based on the provided articles, generate a 'Morning Briefing' for me. "
        "It should include:\n"
        "1. **Top 3-5 Key Developments:** Bullet points highlighting the most important news related to clean energy in Canada, from your skeptical analyst perspective.\n"
        "2. **Key Players/Organizations Mentioned:** List any significant government entities, companies, or individuals.\n"
        "3. **Strategic Implications:** Briefly, what are the potential impacts or what should be watched for?\n"
        "4. **Suggested Reading List:** A list of 2-3 essential articles (title and link) for deeper understanding. Prioritize articles that offer in-depth analysis or critical perspectives.\n\n"
        "Here are the articles for your analysis:\n\n"
    )

    articles_text = []
    for i, article in enumerate(articles):
        title = article.get('title', 'No Title')
        url = article.get('url', '#')
        description = article.get('description', 'No description available.')
        content = article.get('content', '')

        # Prioritize content if available, otherwise use description
        article_summary = f"Title: {title}\nURL: {url}\nDescription: {description}\n"
        if content and len(content) > len(description) * 2: # Use content if substantially longer
             article_summary += f"Content Snippet: {content[:500]}..." # Take a snippet to save tokens
        
        articles_text.append(f"--- Article {i+1} ---\n{article_summary}\n")

    full_prompt = persona_prompt + "\n\n" + analysis_request_prompt + "\n".join(articles_text)

    try:
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        print(f"Error generating content with Gemini: {e}")
        return f"Could not generate briefing: {e}"

def handler(request):
    """
    This is the entry point for our Vercel serverless function.
    It will be triggered and run the news gathering and analysis.
    """
    try:
        print("Starting news gathering and analysis...")
        articles = get_articles_from_newsapi()
        briefing = analyze_and_summarize_with_gemini(articles)
        print("Briefing generated successfully.")
        
        # In a real scenario, you'd send this briefing via email.
        # For PoC, we'll just return it and print it.
        
        # Example: Sending an email (requires setting up a mail service/API)
        # For a PoC, we'll keep it simple and display it.
        # send_email("Your Morning News Briefing", briefing, "your_email@example.com") 

        return briefing # This will be displayed on the Vercel URL
    except Exception as e:
        print(f"An unexpected error occurred in handler: {e}")
        return f"An error occurred: {e}"

# If you want to test locally (optional, for developers)
if __name__ == "__main__":
    # For local testing, ensure NEWS_API_KEY and GEMINI_API_KEY are set in your environment
    # or replace os.environ.get with your actual keys for quick testing (NOT for production)
    # NEWS_API_KEY = "YOUR_NEWS_API_KEY"
    # GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
    
    # Simulate a request
    print(handler(None))
