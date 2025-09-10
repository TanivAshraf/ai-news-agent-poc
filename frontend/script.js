// Initialize Supabase client
// THESE WILL BE REPLACED BY VERCEL ENVIRONMENT VARIABLES IN DEPLOYMENT
const SUPABASE_URL = "YOUR_SUPABASE_URL"; // Replace with your Supabase Project URL
const SUPABASE_ANON_KEY = "YOUR_SUPABASE_ANON_KEY"; // Replace with your Supabase anon key

const supabase = Supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

const newsContainer = document.getElementById('news-container');
const sortOrderSelect = document.getElementById('sortOrder');

async function fetchNews() {
    newsContainer.innerHTML = '<p>Loading news...</p>';
    let { data: articles, error } = await supabase
        .from('articles')
        .select('*')
        .order('published_date', { ascending: false }); // Default sort: newest first

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
            sortedArticles.sort((a, b) => new Date(b.published_date) - new Date(a.published_date));
            break;
        case 'source_asc':
            sortedArticles.sort((a, b) => a.source.localeCompare(b.source));
            break;
        default:
            // Default is already desc by date
            break;
    }

    newsContainer.innerHTML = ''; // Clear existing content

    sortedArticles.forEach(article => {
        const articleDate = article.published_date ? new Date(article.published_date).toLocaleDateString(undefined, {
            year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit'
        }) : 'N/A';

        const keywordsHtml = article.keywords_matched && article.keywords_matched.length > 0
            ? article.keywords_matched.map(keyword => `<span>${keyword}</span>`).join('')
            : '';

        const newsCard = `
            <div class="news-card">
                <h2><a href="${article.url}" target="_blank">${article.title}</a></h2>
                <p class="news-meta">
                    <span><strong>Source:</strong> ${article.source}</span>
                    <span><strong>Published:</strong> ${articleDate}</span>
                </p>
                <p class="news-description">${article.description}</p>
                <div class="news-keywords">${keywordsHtml}</div>
            </div>
        `;
        newsContainer.innerHTML += newsCard;
    });
}

// Event listener for sorting
sortOrderSelect.addEventListener('change', async () => {
    // Fetch again to ensure fresh data and re-sort, or just re-render if data is already loaded
    // For simplicity, we'll re-fetch with a fresh sort
    let { data: articles, error } = await supabase
        .from('articles')
        .select('*'); // Get all articles without specific order
    
    if (!error && articles) {
        renderNews(articles); // Re-render with the new sort
    }
});

// Initial fetch when the page loads
fetchNews();
