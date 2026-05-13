"""Built-in prompt templates for common LLM evaluation scenarios.

Pre-loaded templates cover coding, writing, reasoning, math, and general
evaluation categories, making it easy to start evaluating models immediately.
"""

from typing import Any

SEED_TEMPLATES: list[dict[str, str]] = [
    # -- Coding ---------------------------------------------------------------
    {
        "name": "Code: Implement Binary Search",
        "prompt_text": "Write a Python function that implements binary search on a sorted list. Include docstring, type hints, and handle edge cases (empty list, element not found).",
        "category": "coding",
        "description": "Tests algorithm implementation with edge case handling",
    },
    {
        "name": "Code: Fix Bug in SQL Query",
        "prompt_text": "This SQL query should find users who placed orders in the last 30 days but it has a bug. Find and fix it:\n\nSELECT u.name, COUNT(o.id) as order_count\nFROM users u\nJOIN orders o ON u.id = o.user_id\nWHERE o.created_at > DATE_SUB(NOW(), INTERVAL 30 DAY)\nGROUP BY u.id\nHAVING order_count > 0\nAND u.status != 'inactive';",
        "category": "coding",
        "description": "Tests debugging SQL and understanding query semantics",
    },
    {
        "name": "Code: Design REST API",
        "prompt_text": "Design a REST API for a simple todo application. Include endpoints for creating, reading, updating, and deleting tasks. Provide example request/response JSON for each endpoint. Use proper HTTP status codes.",
        "category": "coding",
        "description": "Tests API design knowledge and REST conventions",
    },
    {
        "name": "Code: Refactor Complex Function",
        "prompt_text": "Refactor this function to be more readable and maintainable:\n\ndef process(data):\n    r = []\n    for i in data:\n        if i.get('type') == 'A':\n            if i.get('val', 0) > 10:\n                r.append({'name': i['n'].upper(), 'score': i['val'] * 2})\n        elif i.get('type') == 'B':\n            if i.get('val', 0) > 5:\n                r.append({'name': i['n'].lower(), 'score': i['val'] * 3})\n    return sorted(r, key=lambda x: x['score'], reverse=True)",
        "category": "coding",
        "description": "Tests ability to refactor unclear code with proper naming and structure",
    },
    # -- Writing --------------------------------------------------------------
    {
        "name": "Write: Email to Decline Meeting",
        "prompt_text": "Write a professional email declining a meeting invitation. The meeting is about Q3 budget planning, but you have a conflicting client presentation. Suggest an alternative time and express willingness to contribute input asynchronously.",
        "category": "writing",
        "description": "Tests professional communication and diplomacy",
    },
    {
        "name": "Write: Product Feature Announcement",
        "prompt_text": "Write a brief product announcement (3-4 paragraphs) for a new dark mode feature in a productivity app. Target audience is existing users. Include: what's new, how to enable it, and key benefits.",
        "category": "writing",
        "description": "Tests marketing writing and user-facing communication",
    },
    {
        "name": "Write: Technical Blog Post Intro",
        "prompt_text": "Write an engaging introduction (200-300 words) for a technical blog post about WebAssembly. The audience is web developers who haven't used WASM yet. Make it accessible but technically accurate.",
        "category": "writing",
        "description": "Tests ability to make technical topics accessible and engaging",
    },
    # -- Reasoning ------------------------------------------------------------
    {
        "name": "Reason: Syllogism Analysis",
        "prompt_text": "Evaluate whether the following conclusion logically follows from the premises:\n\nPremise 1: All birds can fly.\nPremise 2: Penguins are birds.\nConclusion: Penguins can fly.\n\nExplain your reasoning step by step. Then provide a corrected version of Premise 1 that makes all three statements consistent.",
        "category": "reasoning",
        "description": "Tests logical reasoning and identification of false premises",
    },
    {
        "name": "Reason: Cause and Effect",
        "prompt_text": "A city's traffic congestion decreased by 30% after implementing a new bus rapid transit system. However, the city also experienced a 15% increase in remote work due to a corporate policy change, and a new highway bypass opened during the same period.\n\nAnalyze the possible causal relationships. How would you determine which factor contributed most to the traffic reduction? What data would you need?",
        "category": "reasoning",
        "description": "Tests causal reasoning and analytical thinking about confounding variables",
    },
    {
        "name": "Reason: Ethical Dilemma",
        "prompt_text": "A self-driving car must choose between two unavoidable outcomes: swerve to avoid hitting 3 pedestrians but crash into a barrier (likely injuring the passenger), or continue straight (harming the pedestrians but keeping the passenger safe). Discuss the ethical considerations from at least two philosophical perspectives (utilitarian, deontological). What factors should the car's algorithm consider?",
        "category": "reasoning",
        "description": "Tests nuanced ethical reasoning and multi-perspective analysis",
    },
    # -- Math -----------------------------------------------------------------
    {
        "name": "Math: Probability Problem",
        "prompt_text": "You have a bag with 5 red balls, 3 blue balls, and 2 green balls. You draw 3 balls without replacement. What is the probability that you get exactly one ball of each color? Show your work step by step.",
        "category": "math",
        "description": "Tests combinatorial probability calculation",
    },
    {
        "name": "Math: Optimization Problem",
        "prompt_text": "A farmer has 200 meters of fencing and wants to enclose a rectangular field next to a river (so only 3 sides need fencing). What dimensions maximize the area of the field? Prove that your answer is a maximum.",
        "category": "math",
        "description": "Tests optimization with constraints and proof of maximum",
    },
    {
        "name": "Math: Explain Calculus Concept",
        "prompt_text": "Explain the concept of a derivative to someone who understands basic algebra but has never seen calculus. Use a real-world example (like speed and acceleration) to build intuition. Include a simple graphical explanation.",
        "category": "math",
        "description": "Tests mathematical pedagogy and ability to explain abstract concepts",
    },
    # -- General --------------------------------------------------------------
    {
        "name": "General: Summarize Complex Topic",
        "prompt_text": "Explain quantum computing in simple terms. Cover: what it is, how it differs from classical computing, what problems it can solve better, and current limitations. Keep it under 300 words for a general audience.",
        "category": "general",
        "description": "Tests ability to simplify complex topics accurately",
    },
    {
        "name": "General: Multi-step Reasoning",
        "prompt_text": "I'm planning a 2-week trip to Japan for a family of 4 (2 adults, 2 children ages 8 and 12). Budget is $8,000 total. Include flights from San Francisco, accommodation, transportation within Japan, food, and activities. Suggest an itinerary that balances cultural experiences and family-friendly fun.",
        "category": "general",
        "description": "Tests planning, constraint satisfaction, and practical knowledge",
    },
    {
        "name": "General: Compare and Contrast",
        "prompt_text": "Compare and contrast React, Vue, and Svelte for building a medium-sized web application in 2025. Consider: learning curve, performance, ecosystem, developer experience, and long-term maintainability. Provide a clear recommendation for a team of 5 developers with mixed experience levels.",
        "category": "general",
        "description": "Tests balanced technical comparison and practical recommendations",
    },
]


def get_seed_templates() -> list[dict[str, str]]:
    """Return a copy of all built-in seed templates.

    Returns:
        List of template dicts with name, prompt_text, category, and description.
    """
    return [dict(t) for t in SEED_TEMPLATES]


def get_seed_templates_by_category(category: str) -> list[dict[str, str]]:
    """Return seed templates filtered by category.

    Args:
        category: Template category to filter by.

    Returns:
        List of matching template dicts.
    """
    return [dict(t) for t in SEED_TEMPLATES if t["category"] == category]
