def apply_chain_of_density(text):
    """
    Implements the Chain of Density prompting pattern.
    Forces the agent to iteratively summarize and inject more entities per sentence.
    Useful for creating hyper-dense research briefs.
    """
    return f"""
    ARTICLE: {text}
    
    INSTRUCTIONS:
    1. Write a baseline 3-sentence summary.
    2. Identify 5 missing specific entities (names, dates, metrics) from the article.
    3. Rewrite the summary, keeping the exact same length, but cramming the 5 entities in.
    4. Repeat this density process 3 times.
    
    OUTPUT FORMAT: JSON array of 4 summaries, progressively denser.
    """\n