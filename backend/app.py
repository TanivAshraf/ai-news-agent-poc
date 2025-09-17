# backend/app.py

import os
import requests
import feedparser
import google.generativeai as genai
from datetime import datetime, timedelta, date
import re
from supabase import create_client, Client
from bs4 import BeautifulSoup

# --- Configuration (Get these from your environment variables) ---
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") # service_role key
SCRAPINGBEE_API_KEY = os.environ.get("SCRAPINGBEE_API_KEY")

# --- Helper for Date Parsing ---
def _parse_date_string(date_string):
    """
    Attempts to parse a date string into a datetime object using common formats.
    Returns datetime.min if parsing fails.
    """
    if not date_string:
        return datetime.min

    formats = [
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S%z',
        '%a, %d %b %Y %H:%M:%S %z',
        '%a, %d %b %Y %H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
    ]

    cleaned_date_string = date_string.replace('Z', '+00:00').strip()
    cleaned_date_string = re.sub(r' (UTC|GMT)$', ' +0000', cleaned_date_string, flags=re.IGNORECASE)

    for fmt in formats:
        try:
            dt_obj = datetime.strptime(cleaned_date_string, fmt)
            if dt_obj.tzinfo is None:
                return dt_obj.replace(tzinfo=datetime.timezone.utc)
            return dt_obj
        except ValueError:
            pass

    print(f"Warning: Could not parse date string '{date_string}' with any known format.")
    return datetime.min

# --- Configure Google Gemini ---
def get_gemini_model():
    """
    Configures Google Gemini and finds a suitable model, prioritizing 'gemini-1.5-flash'.
    """
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY is not set. Cannot configure Gemini.")
        return None

    genai.configure(api_key=GEMINI_API_KEY)
    
    available_models = []
    try:
        available_models = list(genai.list_models())
    except Exception as e:
        print(f"Error listing Gemini models: {e}. Check API key validity and network access.")
        return None

    # Priority 1: Try 'models/gemini-1.5-flash' for efficiency
    for m in available_models:
        if m.name == 'models/gemini-1.5-flash' and 'generateContent' in m.supported_generation_methods:
            print("Found suitable Gemini model: models/gemini-1.5-flash (preferred).")
            return genai.GenerativeModel('gemini-1.5-flash')
            
    # Priority 2: Fallback to 'models/gemini-pro' (older, but usually available)
    for m in available_models:
        if m.name == 'models/gemini-pro' and 'generateContent' in m.supported_generation_methods:
            print("Found suitable Gemini model: models/gemini-pro (fallback).")
            return genai.GenerativeModel('gemini-pro')

    # Priority 3: Fallback to 'models/gemini-1.5-pro' if others aren't available or suitable
    for m in available_models:
        if m.name == 'models/gemini-1.5-pro' and 'generateContent' in m.supported_generation_methods:
            print("Found suitable Gemini model: models/gemini-1.5-pro (general fallback).")
            return genai.GenerativeModel('gemini-1.5-pro')

    # Priority 4: General fallback - find ANY model that supports generateContent
    print("No specific preferred models found. Searching for any 'generateContent' supporting model.")
    for m in available_models:
        if 'generateContent' in m.supported_generation_methods:
            print(f"Found suitable Gemini model: {m.name} (any available).")
            return genai.GenerativeModel(m.name.split('/')[-1])

    print("No suitable Gemini model found that supports 'generateContent'. AI analysis will be skipped.")
    return None

model = get_gemini_model() # Initialize the model dynamically

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- Keywords for Filtering (Case-insensitive) ---
# TEMPORARILY SIMPLIFIED KEYWORDS FOR DEBUGGING "0 articles found" ISSUE
KEYWORDS = [
    "Canada", "Canadian", "Energy", "clean energy", "economy", "Ontario", "Alberta", "Quebec", "Toronto", "Vancouver"
]
KEYWORD_PATTERN = re.compile(r'\b(?:' + '|'.join(re.escape(k) for k in KEYWORDS) + r')\b', re.IGNORECASE)

def fetch_articles_from_rss():
    """Fetches articles from the configured RSS feeds."""
    all_articles = []
    print("Fetching articles from RSS feeds...")
    RSS_FEEDS = [
        {"name": "Globe and Mail - Business", "url": "https://www.theglobeandmail.com/business/feed/"},
        {"name": "Toronto Star - Business", "url": "https://www.thestar.com/business/feed/"},
        {"name": "National Observer", "url": "https://www.nationalobserver.com/rss"},
        # --- {"name": "Financial Post", "url": "https://financialpost.com/feed/"}, ---
        {"name": "Ontario Newsroom", "url": "https://news.ontario.ca/en/feed"},
        {"name": "The Hub", "url": "https://thehub.ca/feed/"},
        {"name": "The Logic", "url": "https://thelogic.co/feed/"},
    ]
    for feed_info in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries:
                title = entry.title if hasattr(entry, 'title') else 'No Title'
                link = entry.link if hasattr(entry, 'link') else '#'
                summary = entry.summary if hasattr(entry, 'summary') else (entry.description if hasattr(entry, 'description') else 'No summary available.')
                
                matched_keywords = [k for k in KEYWORDS if re.search(r'\b' + re.escape(k) + r'\b', title + ' ' + summary, re.IGNORECASE)]

                if matched_keywords:
                    all_articles.append({
                        "source": feed_info["name"],
                        "title": title,
                        "url": link,
                        "description": summary,
                        "published_date": entry.published if hasattr(entry, 'published') else 'N/A',
                        "keywords_matched": matched_keywords,
                        "full_content": None
                    })
        except Exception as e:
            print(f"Error fetching RSS for {feed_info['name']} ({feed_info['url']}): {e}")
    print(f"Found {len(all_articles)} articles from RSS feeds after initial keyword filter.")
    return all_articles

def fetch_articles_from_newsapi(query="", days_back=1, language="en", max_articles=10):
    """
    Fetches articles from News API for a given query (as a supplementary source).
    Uses simplified query for debugging.
    """
    if not NEWS_API_KEY:
        print("NEWS_API_KEY is not set, skipping News API fetch.")
        return []

    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)

    # TEMPORARILY SIMPLIFIED NEWSAPI QUERY FOR DEBUGGING
    newsapi_query = "Canada AND (clean energy OR energy OR economy)" 

    url = f"https://newsapi.org/v2/everything"
    params = {
        "q": newsapi_query,
        "language": language,
        "from": start_date.isoformat(),
        "to": end_date.isoformat(),
        "sortBy": "relevancy",
        "pageSize": max_articles,
        "apiKey": NEWS_API_KEY
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        if data['status'] == 'ok':
            formatted_articles = []
            for article in data['articles']:
                title = article.get('title', 'No Title')
                description = article.get('description', 'No description available.')
                # Filter using the combined KEYWORDS (including geographical)
                matched_keywords = [k for k in KEYWORDS if re.search(r'\b' + re.escape(k) + r'\b', title + ' ' + description, re.IGNORECASE)]

                if matched_keywords:
                    formatted_articles.append({
                        "source": article.get('source', {}).get('name', 'News API'),
                        "title": title,
                        "url": article.get('url', '#'),
                        "description": description,
                        "published_date": article.get('publishedAt', 'N/A'),
                        "keywords_matched": matched_keywords,
                        "full_content": None
                    })
                print(f"Found {len(formatted_articles)} articles from News API.")
            return formatted_articles
        else:
            print(f"News API Error: {data.get('message', 'Unknown error')}")
            return []
    except requests.exceptions.RequestException as e:
        print(f"Error fetching news from News API: {e}")
        return []

def fetch_full_article_content(url):
    """
    Fetches the full HTML content of an article URL using ScrapingBee
    and extracts main text using BeautifulSoup.
    """
    if not SCRAPINGBEE_API_KEY:
        print("SCRAPINGBEE_API_KEY is not set. Skipping full content fetch.")
        return None

    print(f"Attempting to fetch full content for: {url}")
    scrapingbee_url = "https://app.scrapingbee.com/api/v1/"
    params = {
        "api_key": SCRAPINGBEE_API_KEY,
        "url": url,
    }

    try:
        response = requests.get(scrapingbee_url, params=params, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        main_content = soup.find('article') or soup.find('main') or soup.find(class_=re.compile("body|content|article", re.I))
        
        if main_content:
            for script_or_style in main_content(['script', 'style']):
                script_or_style.extract()
            text = main_content.get_text(separator='\n', strip=True)
            print(f"Successfully fetched and extracted content for: {url[:50]}...")
            return text
        else:
            print(f"Could not find main content for: {url[:50]}... Returning raw text.")
            return soup.get_text(separator='\n', strip=True)

    except requests.exceptions.RequestException as e:
        print(f"Error fetching full content for {url[:50]}... with ScrapingBee: {e}")
        if response is not None:
            print(f"ScrapingBee response text: {response.text[:500]}...")
        return None
    except Exception as e:
        print(f"Error processing full content for {url[:50]}...: {e}")
        return None

def store_articles_in_supabase(all_articles):
    """Stores unique aggregated articles into Supabase."""
    if not all_articles:
        print("No articles to store in 'articles' table.")
        return 0

    unique_articles = {article['url']: article for article in all_articles}.values()
    articles_to_insert = []

    for article in unique_articles:
        parsed_datetime = _parse_date_string(article['published_date'])
        
        if parsed_datetime != datetime.min:
            if parsed_datetime.tzinfo is None:
                formatted_date = parsed_datetime.isoformat() + '+00:00'
            else:
                formatted_date = parsed_datetime.isoformat()
        else:
            formatted_date = None

        articles_to_insert.append({
            "source": article.get('source'),
            "title": article.get('title'),
            "url": article.get('url'),
            "description": article.get('description'),
            "published_date": formatted_date,
            "keywords_matched": article.get('keywords_matched', [])
        })

    if articles_to_insert:
        try:
            response = supabase.table('articles').upsert(articles_to_insert, on_conflict='url').execute()
            print(f"Successfully upserted {len(response.data)} articles into 'articles' table.")
            return len(response.data)
        except Exception as e:
            print(f"Error inserting into Supabase 'articles' table: {e}")
            return 0
    else:
        return 0

def analyze_and_brief_with_gemini(articles_for_analysis):
    """
    Uses Gemini to analyze articles and generate a consolidated daily briefing.
    Prioritizes full content from ScrapingBee for deeper analysis.
    """
    if not model:
        print("Gemini model not initialized. Skipping AI analysis.")
        return None

    if not articles_for_analysis:
        print("No articles to analyze for the daily briefing.")
        return None

    sorted_articles = sorted(
        articles_for_analysis, 
        key=lambda x: _parse_date_string(x.get('published_date')), 
        reverse=True
    )
    
    MAX_ARTICLES_FOR_DEEP_ANALYSIS = 3 
    articles_for_gemini_input = []
    related_urls_for_briefing = []

    print(f"Preparing input for Gemini from top {MAX_ARTICLES_FOR_DEEP_ANALYSIS} articles (using full content if available).")

    for i, article in enumerate(sorted_articles):
        article_copy = dict(article)
        
        title = article_copy.get('title', 'No Title')
        url = article_copy.get('url', '#')
        description = article_copy.get('description', 'No description available.')
        full_content = article_copy.get('full_content')

        article_input_text = ""
        if i < MAX_ARTICLES_FOR_DEEP_ANALYSIS and full_content:
            article_input_text = f"Title: {title}\nURL: {url}\nFull Content: {full_content[:2000]}..."
        else:
            article_input_text = f"Title: {title}\nURL: {url}\nDescription: {description}"
        
        articles_for_gemini_input.append(f"--- Article {i+1} ---\n{article_input_text}\n")
        related_urls_for_briefing.append(url)

    current_date_str = date.today().strftime('%B %d, %Y')

    persona = (
        "You are a senior political analyst for 'New Economy Canada'. "
        "Your raison d’etre is to ramp up awareness of and support for solutions "
        "and good things happening in the clean economy. "
        "You communicate the urgency for Canada to act now to remain relevant in the global economy. "
        "You are trying to accelerate the clean energy transition and make Canada a leader in this transition. "
        "You always look for concrete policy actions, investment trends, and potential challenges or 'greenwashing'. "
    )

    task_instruction = (
        f"Based on the following news articles, generate a 'Morning Briefing' for **{current_date_str}**. "
        "Some articles may include 'Full Content' for deeper analysis. "
        "Your output should be structured to help 'New Economy Canada' monitor, observe, and react to news, "
        "and understand the narrative being shaped. "
        "Prioritize quality and focus. Here's the structure I need:\n\n"
        f"**Briefing Title:** AI Morning Briefing - {current_date_str}\n\n"
        "**Executive Summary:** A concise overview of the most critical developments (2-3 sentences).\n\n"
        "**Key Developments:**\n"
        "- [Bullet point 1: Major news item, e.g., 'Government announces X funding for Y project']\n"
        "- [Bullet point 2: Key policy shift, e.g., 'New provincial legislation on Z']\n"
        "- [Bullet point 3: Industry trends or notable investments, e.g., 'Company A invests in B technology']\n"
        "- ... (up to 5 bullet points)\n\n"
        "**Strategic Implications for New Economy Canada:** (Analyze potential impacts, what to watch for, narrative shaping elements)\n"
        "- [Implication 1]\n"
        "- [Implication 2]\n\n"
        "**Suggested Reactions:** (Based on the news, recommend positive or concerned tones)\n"
        "- **Positive:** [If supportive public policy, funding, etc., suggest an action/stance]\n"
        "- **Concerned:** [If harmful public policy, 'greenwashing', etc., suggest an action/stance]\n\n"
        "**Relevant Article URLs:**\n"
        "- [Link 1: Brief description]\n"
        "- [Link 2: Brief description]\n"
        "- ...\n\n"
        "Here are the articles for your analysis:\n\n"
    )

    full_prompt = persona + "\n\n" + task_instruction + "\n".join(articles_for_gemini_input)

    try:
        print(f"Sending articles to Gemini model '{model.model_name}' for analysis...")
        response = model.generate_content(full_prompt)
        briefing_text = response.text
        print("Gemini analysis complete.")
        
        briefing_data = parse_gemini_briefing(briefing_text, related_urls_for_briefing)
        briefing_data['raw_ai_response'] = briefing_text
        return briefing_data

    except Exception as e:
        print(f"Error generating content with Gemini: {e}")
        return {
            "title": f"AI Briefing Error - {date.today().strftime('%Y-%m-%d')}",
            "summary_text": f"Error during AI analysis: {e}. Raw AI response might be incomplete or empty.",
            "key_developments": [],
            "strategic_implications": "Could not perform full analysis due to AI error.",
            "suggested_reactions": "Monitor AI service status.",
            "related_article_urls": related_urls_for_briefing,
            "raw_ai_response": f"Error: {e}\nPrompt: {full_prompt}"
        }

def parse_gemini_briefing(briefing_text, related_urls):
    current_date_str = date.today().strftime('%B %d, %Y')

    parsed_data = {
        "title": f"AI Morning Briefing - {current_date_str}",
        "summary_text": "",
        "key_developments": [],
        "strategic_implications": "",
        "suggested_reactions": "",
        "related_article_urls": related_urls
    }

    sections = {
        "Briefing Title": r"^\*\*Briefing Title:\*\* (.*?)$",
        "Executive Summary": r"^\*\*Executive Summary:\*\*\s*(.*?)(?=\n\n\*\*Key Developments\*\*|$)",
        "Key Developments": r"^\*\*Key Developments:\*\*\s*(.*?)(?=\n\n\*\*Strategic Implications\*\*|$)",
        "Strategic Implications for New Economy Canada": r"^\*\*Strategic Implications for New Economy Canada:\*\*\s*(.*?)(?=\n\n\*\*Suggested Reactions\*\*|$)",
        "Suggested Reactions": r"^\*\*Suggested Reactions:\*\*\s*(.*?)(?=\n\n\*\*Relevant Article URLs\*\*|$)",
    }

    title_match = re.search(sections["Briefing Title"], briefing_text, re.MULTILINE)
    if title_match:
        extracted_title = title_match.group(1).strip()
        if re.search(r'\d{4}-\d{2}-\d{2}', extracted_title) or "Today's Date" in extracted_title or "October 26, 2023" in extracted_title:
            parsed_data["title"] = f"AI Morning Briefing - {current_date_str}"
        else:
            parsed_data["title"] = extracted_title
    
    summary_match = re.search(sections["Executive Summary"], briefing_text, re.DOTALL | re.MULTILINE)
    if summary_match:
        parsed_data["summary_text"] = summary_match.group(1).strip()

    dev_match = re.search(sections["Key Developments"], briefing_text, re.DOTALL | re.MULTILINE)
    if dev_match:
        dev_text = dev_match.group(1)
        parsed_data["key_developments"] = [item.strip() for item in re.findall(r'^- (.+)$', dev_text, re.MULTILINE)]
    
    imp_match = re.search(sections["Strategic Implications for New Economy Canada"], briefing_text, re.DOTALL | re.MULTILINE)
    if imp_match:
        parsed_data["strategic_implications"] = imp_match.group(1).strip()

    react_match = re.search(sections["Suggested Reactions"], briefing_text, re.DOTALL | re.MULTILINE)
    if react_match:
        parsed_data["suggested_reactions"] = react_match.group(1).strip()

    return parsed_data

def store_briefing_in_supabase(briefing_data):
    """Stores the AI-generated briefing into the 'daily_briefings' table."""
    if not briefing_data:
        print("No briefing data to store.")
        return "No briefing processed."

    briefing_to_insert = {
        "briefing_date": date.today().isoformat(),
        "title": briefing_data.get("title"),
        "summary_text": briefing_data.get("summary_text"),
        "key_developments": briefing_data.get("key_developments"),
        "strategic_implications": briefing_data.get("strategic_implications"),
        "suggested_reactions": briefing_data.get("suggested_reactions"),
        "related_article_urls": briefing_data.get("related_article_urls"),
        "raw_ai_response": briefing_data.get("raw_ai_response")
    }

    try:
        response = supabase.table('daily_briefings').upsert(
            briefing_to_insert, 
            on_conflict='briefing_date'
        ).execute()
        
        print(f"Successfully stored/updated daily briefing in Supabase: {response.data}")
        return "Daily briefing stored successfully."
    except Exception as e:
        print(f"Error storing daily briefing in Supabase: {e}")
        return f"Error storing daily briefing: {e}"

def handler(request):
    """
    Main handler for the GitHub Actions workflow.
    Fetches news, stores individual articles, then generates and stores a daily briefing.
    """
    print("Starting AI News Agent (with Brain)...")
    
    # 1. Fetch articles from RSS feeds
    rss_articles = fetch_articles_from_rss()

    # 2. Fetch articles from News API (supplementary)
    newsapi_articles = fetch_articles_from_newsapi() 
    
    # 3. Combine all fetched articles and deduplicate
    all_fetched_articles = rss_articles + newsapi_articles
    
    # 4. Fetch full content for a limited number of top articles
    # Sort them by date to get the most recent for full content.
    sorted_articles = sorted(
        all_fetched_articles,
        key=lambda x: _parse_date_string(x.get('published_date')),
        reverse=True
    )
    
    articles_with_full_content = []
    MAX_SCRAPINGBEE_CALLS = 3 
    MAX_ARTICLES_FOR_GEMINI = 3

    for i, article in enumerate(sorted_articles):
        article_copy = dict(article) 
        if i < MAX_SCRAPINGBEE_CALLS:
            full_text = fetch_full_article_content(article_copy['url'])
            if full_text:
                article_copy['full_content'] = full_text
        articles_with_full_content.append(article_copy)

    articles_for_gemini_analysis = articles_with_full_content[:MAX_ARTICLES_FOR_GEMINI]

    # 5. Store individual articles in the 'articles' table (for historical record/raw data)
    articles_stored_count = store_articles_in_supabase(all_fetched_articles) 
    print(f"Stored {articles_stored_count} unique articles in 'articles' table.")

    # 6. Analyze articles with Gemini to create the daily briefing
    if model:
        briefing_data = analyze_and_brief_with_gemini(articles_for_gemini_analysis)
        briefing_result = store_briefing_in_supabase(briefing_data)
    else:
        error_briefing = {
            "title": f"AI Briefing Initialization Error - {date.today().strftime('%Y-%m-%d')}",
            "summary_text": "Gemini model could not be initialized, likely due to API key issues or model unavailability. Please check backend logs.",
            "key_developments": [],
            "strategic_implications": "AI analysis skipped.",
            "suggested_reactions": "Check Gemini API key and model availability.",
            "related_article_urls": [a.get('url', '#') for a in all_fetched_articles],
            "raw_ai_response": "Model initialization failed."
        }
        briefing_result = store_briefing_in_supabase(error_briefing)
        print(f"Gemini model could not be initialized, skipping AI analysis. Briefing storage status: {briefing_result}")


    print(f"Full run complete. Briefing storage status: {briefing_result}")
    return f"AI Agent run completed. Articles: {articles_stored_count}, Briefing: {briefing_result}"

if __name__ == "__main__":
    print(handler(None))
