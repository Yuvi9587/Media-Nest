import re

def get_best_match(token, cur):
    query = """
        SELECT t.tag_name, t.tag_type, COUNT(it.hash) as cnt
        FROM Tags t
        LEFT JOIN ImageTags it ON t.tag_id = it.tag_id
        WHERE t.tag_name LIKE ?
        GROUP BY t.tag_id
        ORDER BY cnt DESC
        LIMIT 1
    """
    cur.execute(query, (f"%{token}%",))
    res = cur.fetchone()
    if res:
        return res[0], res[1]
    return None, None

def parse_natural_language_query(query: str, cur) -> list[str]:
    """
    Parses a natural language string into a list of actual database tags.
    - Tokenizes the query.
    - Removes stop words.
    - Uses a greedy n-gram matching (bigrams first) to find the best DB tags.
    - Returns a list of required tags.
    """
    if query.lower().startswith("search:"):
        query = query[7:].strip()
        
    raw_words = re.findall(r'\b\w+\b', query.lower())
    words = [w for w in raw_words if w not in STOP_WORDS and len(w) > 1]
    
    if not words:
        return []
        
    matched_tags = []
    consumed_indices = set()
    
    # 1. Check bigrams (greedy)
    for i in range(len(words) - 1):
        if i in consumed_indices or (i+1) in consumed_indices:
            continue
        bigram = f"{words[i]}_{words[i+1]}"
        best_name, best_type = get_best_match(bigram, cur)
        if best_name:
            matched_tags.append((best_name, best_type))
            consumed_indices.add(i)
            consumed_indices.add(i+1)
            
    # 2. Check unigrams
    for i in range(len(words)):
        if i in consumed_indices:
            continue
        unigram = words[i]
        best_name, best_type = get_best_match(unigram, cur)
        if best_name:
            matched_tags.append((best_name, best_type))
            
    # 3. Classify into required and optional
    final_tags = []
    has_required = any(t[1] in ('character', 'series', 'artist', 'copyright', 'parody') for t in matched_tags)
    
    for name, tag_type in matched_tags:
        if tag_type in ('character', 'series', 'artist', 'copyright', 'parody'):
            final_tags.append(name) # Required
        else:
            if has_required:
                final_tags.append(f"~{name}") # Optional if there are required tags
            else:
                final_tags.append(name) # Required if no character tags present
            
    return final_tags

STOP_WORDS = {
    'a', 'an', 'the', 'in', 'on', 'at', 'by', 'for', 'with', 'about', 'against',
    'between', 'into', 'through', 'during', 'before', 'after', 'above', 'below',
    'to', 'from', 'up', 'down', 'in', 'out', 'on', 'off', 'over', 'under', 'again',
    'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all',
    'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor',
    'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 's', 't', 'can', 'will',
    'just', 'don', 'should', 'now', 'i', 'me', 'my', 'myself', 'we', 'our', 'ours',
    'ourselves', 'you', 'your', 'yours', 'yourself', 'yourselves', 'he', 'him', 'his',
    'himself', 'she', 'her', 'hers', 'herself', 'it', 'its', 'itself', 'they', 'them',
    'their', 'theirs', 'themselves', 'what', 'which', 'who', 'whom', 'this', 'that',
    'these', 'those', 'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have',
    'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'and', 'but', 'if', 'or',
    'because', 'as', 'until', 'while', 'of', 'like', 'search', 'find', 'show', 'showing' 
}
