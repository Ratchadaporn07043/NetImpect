"""
Test Tasks (Benchmarks)
=========================
Separated from scenarios.py so that scenarios.py contains only network scenarios.
This file contains the task prompts used to test the multi-agent workflow.

Adds Ground Truth / Rubric data for post-workflow evaluation:
- The Reviewer still checks the Worker during the conversation.
- The ground-truth evaluator checks only the final answer and does not assist during execution.
"""

TASKS = {
    "coding_task": (
        "Write a Python function named `is_prime(n)` that accepts an integer and returns True/False "
        "to indicate whether it is prime, with a brief explanation."
    ),
    "research_summary": (
        "Summarize the advantages and disadvantages of Retrieval-Augmented Generation (RAG) "
        "compared with directly fine-tuning a model, in no more than 5 points."
    ),
    "data_analysis": (
        "Assume 12 months of monthly sales data. Propose a trend-analysis method "
        "and identify the chart type that communicates the result best."
    ),
    "planning_decision": (
        "A team can invest in one of three options: (1) improve UX, "
        "(2) add a new feature, or (3) fix existing bugs. Recommend what to prioritize "
        "and give a brief rationale."
    ),
}

TASK_GROUND_TRUTH = {
    "coding_task": {
        "max_score": 5,
        "pass_score": 4,
        "rubric": [
            "Defines a function named is_prime(n)",
            "Returns boolean True/False",
            "Handles n <= 1 as False",
            "Handles 2 as True and even numbers greater than 2 as False",
            "Checks divisors through sqrt(n) or i*i <= n for efficiency",
            "Includes a brief explanation",
        ],
        "checks": [
            {"id": "function_name", "description": "Identifies the is_prime function", "any": ["is_prime"]},
            {"id": "boolean_return", "description": "Returns True/False", "any": ["True", "False", "boolean"]},
            {"id": "n_le_1", "description": "Explains or handles n <= 1", "any": ["<= 1", "< 2", "less than 2", "1 is not", "0 is not"]},
            {"id": "two_case", "description": "Handles the number 2", "any": ["n == 2", "equal to 2", "2 is", "2 ="]},
            {"id": "sqrt_bound", "description": "Checks through the square root or i*i <= n", "any": ["sqrt", "square root", "i * i", "i*i", "** 0.5", "squared"]},
            {"id": "explanation", "description": "Includes a principle explanation", "any": ["principle", "because", "divisor", "prime"]},
        ],
    },
    "research_summary": {
        "max_score": 5,
        "pass_score": 4,
        "rubric": [
            "Compares RAG with fine-tuning directly",
            "Mentions RAG advantages such as easy knowledge updates, reduced hallucination, or source citations",
            "Mentions RAG disadvantages such as latency, retrieval quality, or infrastructure complexity",
            "Mentions fine-tuning advantages such as adapting style, behavior, or domain patterns",
            "Mentions fine-tuning disadvantages such as cost, training data, or difficult knowledge updates",
            "Stays within approximately five points and summarizes the key message",
        ],
        "checks": [
            {"id": "rag_mentioned", "description": "Mentions RAG", "any": ["RAG", "Retrieval-Augmented", "retrieval"]},
            {"id": "fine_tune_mentioned", "description": "Mentions fine-tuning", "any": ["fine-tune", "fine tune", "fine-tuning"]},
            {"id": "rag_advantage", "description": "Includes a RAG advantage", "any": ["update", "source", "citation", "reduced hallucination", "new knowledge"]},
            {"id": "rag_disadvantage", "description": "Includes a RAG disadvantage", "any": ["latency", "retrieval", "complex", "infrastructure", "data quality"]},
            {"id": "finetune_advantage", "description": "Includes a fine-tuning advantage", "any": ["style", "behavior", "domain", "specialized", "pattern"]},
            {"id": "finetune_disadvantage", "description": "Includes a fine-tuning disadvantage", "any": ["cost", "training data", "train", "hard to update", "outdated"]},
        ],
    },
    "data_analysis": {
        "max_score": 5,
        "pass_score": 4,
        "rubric": [
            "Orders 12 months of sales data chronologically",
            "Analyzes the overall trend, such as growth, decline, seasonality, or outliers",
            "Recommends a line chart as the primary time-series chart",
            "May add a moving average or month-over-month comparison",
            "Communicates the analysis steps systematically",
        ],
        "checks": [
            {"id": "time_order", "description": "Mentions monthly data or chronological order", "any": ["monthly", "12 months", "time", "time series", "month"]},
            {"id": "trend", "description": "Mentions trend", "any": ["trend", "increase", "decrease", "growth", "decline"]},
            {"id": "line_chart", "description": "Recommends a line chart", "any": ["line chart", "line graph"]},
            {"id": "seasonality_outlier", "description": "Considers seasonality or outliers", "any": ["season", "outlier", "anomal", "spike", "drop"]},
            {"id": "moving_average", "description": "Mentions moving average or month-over-month comparison", "any": ["moving average", "MoM", "month-over-month", "percentage change"]},
        ],
    },
    "planning_decision": {
        "max_score": 5,
        "pass_score": 4,
        "rubric": [
            "Clearly selects one investment or provides a prioritized list with a first choice",
            "Provides reasoning based on impact, urgency, risk, or customer value",
            "Considers trade-offs among UX, a new feature, and existing bugs",
            "Provides a short action plan such as assessing data, measuring results, or running a sprint",
            "The answer is actionable and suitable for team decision-making",
        ],
        "checks": [
            {"id": "clear_choice", "description": "Makes a clear choice or prioritization", "any": ["recommend", "first", "before", "prioritize", "choose"]},
            {"id": "mentions_options", "description": "Mentions the main options", "any": ["UX", "feature", "bug"]},
            {"id": "impact_reason", "description": "Provides impact or customer reasoning", "any": ["impact", "customer", "user", "value"]},
            {"id": "risk_urgency", "description": "Provides risk or urgency reasoning", "any": ["risk", "urgency", "blocked", "damage", "technical debt"]},
            {"id": "action_plan", "description": "Provides an action plan", "any": ["plan", "step", "sprint", "measure", "assess", "roadmap"]},
        ],
    },
}
