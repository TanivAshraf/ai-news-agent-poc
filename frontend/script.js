// script.js

// Initialize Supabase client with your project details
// IMPORTANT: For a production application, these keys should ideally be loaded
// from environment variables via a build step (e.g., using a framework like Next.js).
// For this static HTML/JS PoC, directly embedding the public anon key is common,
// but be aware of the security implications for highly sensitive data in a public repo.
const SUPABASE_URL = "https://zdcliufkeprmrkxmqifr.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpkY2xpdWZrZXBybXJreG1xaWZyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTU2Njg0OTEsImV4cCI6MjA3MTI0NDQ5MX0.M8I8qk-oh8H3tZ8-KWHXfoN_p5jhdfRq-4j0OEbiO_s";

const supabase = Supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

const newsContainer = document.getElementById('news-container');
const sortOrderSelect = document.getElementById('sortOrder');

async function fetchNewsAndRender() {
    newsContainer.innerHTML = '<p>Loading news...</p>';
    
    let { data: articles, error } = await supabase
        .from('articles')
        .select('*'); // Fetch all relevant columns

    if (error) {
        console.error('Error fetching articles:', error.message);
        newsContainer.innerHTML = '<p>Failed to load news. Please try again later.</p>';
        return;
    }

    if (articles.length === 0) {
        newsContainer.innerHTML = '<p>No relevant news found today.</p>';
        return;
    }

    renderNews(articles);
}

function renderNews(articles) {
    // Apply sorting based on the selected option
    const sortOrder = sortOrderSelect.value;
    let sortedArticles = [...articles]; // Create a shallow copy to sort

    switch (sortOrder) {
        case 'published_date_asc':
            sortedArticles.sort((a, b) => new Date(a.published_date) - new Date(b.published_date));
            break;
        case 'published_date_desc':
            // Ensure valid dates for sorting, fall back to epoch if invalid
            sortedArticles.sort((a, b) => {
                const dateA = a.published_date ? new Date(a.published_date) : new Date(0);
                const dateB = b.published_date ? new Date(b.published_date) : new Date(0);
                return dateB - dateA;
            });
            break;
        case 'source_asc':
            sortedArticles.sort((a, b) => (a.source || '').localeCompare(b.source || '')); // Handle null sources
            break;
        default:
            // Default is already desc by date, so no action needed if it's the default
            break;
    }

    newsContainer.innerHTML = ''; // Clear existing content

    sortedArticles.forEach(article => {
        // Format published_date for display
        const articleDate = article.published_date ? new Date(article.published_date).toLocaleDateString(undefined, {
            year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
        }) : 'N/A';

        // Display keywords as tags
        const keywordsHtml = article.keywords_matched && article.keywords_matched.length > 0
            ? article.keywords_matched.map(keyword => `<span>${keyword}</span>`).join('')
            : '';

        const newsCard = `
            <div class="news-card">
                <h2><a href="${article.url}" target="_blank">${article.title}</a></h2>
                <p class="news-meta">
                    <span><strong>Source:</strong> ${article.source || 'Unknown'}</span>
                    <span><strong>Published:</strong> ${articleDate}</span>
                </p>
                <p class="news-description">${article.description || 'No description available.'}</p>
                <div class="news-keywords">${keywordsHtml}</div>
            </div>
        `;
        newsContainer.innerHTML += newsCard;
    });
}

// Event listener for sorting dropdown
sortOrderSelect.addEventListener('change', fetchNewsAndRender);

// Initial fetch when the page loads
fetchNewsAndRender();
