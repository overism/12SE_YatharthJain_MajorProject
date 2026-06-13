"""
RAG/syllabus_topics.py — NSW HSC syllabus topic reference

Used by the Quiz Generator modal so students pick an actual syllabus
topic *name* instead of typing an ambiguous module code (e.g. "8.2"),
which was causing Gemini to generate quizzes on the wrong topic.

Structure:
SYLLABUS_TOPICS = {
    "<Subject Name>": [
        {"module": "<Module name>", "topics": ["<Topic 1>", "<Topic 2>", ...]},
        ...
    ]
}

This list is curated, not exhaustive — extend it as needed. The Quiz
modal automatically picks up new entries.
"""

SYLLABUS_TOPICS = {
    "Physics": [
        {
            "module": "Module 5 — Advanced Mechanics",
            "topics": [
                "Projectile Motion",
                "Circular Motion",
                "Motion in Gravitational Fields",
            ],
        },
        {
            "module": "Module 6 — Electromagnetism",
            "topics": [
                "Charged Particles, Conductors and Electric/Magnetic Fields",
                "The Motor Effect",
                "Electromagnetic Induction",
            ],
        },
        {
            "module": "Module 7 — The Nature of Light",
            "topics": [
                "Electromagnetic Spectrum",
                "Light: Wave Model",
                "Light: Quantum Model",
                "Light and Special Relativity",
            ],
        },
        {
            "module": "Module 8 — From the Universe to the Atom",
            "topics": [
                "Models of the Atom (Rutherford, Bohr, Atomic Structure Experiments)",
                "Properties of the Nucleus (Radioactivity, Decay, Mass-Energy)",
                "Deep Inside the Nucleus (Standard Model)",
                "Origins of the Elements (Stellar Nucleosynthesis)",
            ],
        },
    ],
    "Chemistry": [
        {
            "module": "Module 5 — Equilibrium and Acid Reactions",
            "topics": ["Static and Dynamic Equilibrium", "Factors Affecting Equilibrium", "Quantitative Analysis"],
        },
        {
            "module": "Module 6 — Acid/Base Reactions",
            "topics": ["Properties of Acids and Bases", "Brønsted-Lowry Theory", "Quantitative Analysis of Acids and Bases"],
        },
        {
            "module": "Module 7 — Organic Chemistry",
            "topics": ["Nomenclature", "Hydrocarbons", "Reactions of Organic Molecules", "Polymers"],
        },
        {
            "module": "Module 8 — Applying Chemical Ideas",
            "topics": ["Analysis of Inorganic Substances", "Analysis of Organic Substances", "Chemical Synthesis and Design"],
        },
    ],
    "Mathematics Advanced": [
        {
            "module": "Functions",
            "topics": ["Working with Functions", "Polynomials", "Other Graphs and Relationships"],
        },
        {
            "module": "Trigonometric Functions",
            "topics": ["Trigonometric Functions and Identities", "Trigonometric Equations", "Graphs of Trigonometric Functions"],
        },
        {
            "module": "Calculus",
            "topics": ["Differentiation", "Applications of Differentiation", "Integration"],
        },
        {
            "module": "Exponential and Logarithmic Functions",
            "topics": ["Exponential and Logarithmic Laws", "Growth and Decay Applications"],
        },
        {
            "module": "Statistical Analysis",
            "topics": ["Discrete Probability Distributions", "The Normal Distribution", "Bivariate Data Analysis"],
        },
        {
            "module": "Financial Mathematics",
            "topics": ["Compound Interest and Depreciation", "Annuities and Loan Repayments"],
        },
    ],
    "English Advanced": [
        {
            "module": "Common Module — Texts and Human Experiences",
            "topics": ["Prescribed Text Analysis", "Related Texts and Personal Experience"],
        },
        {
            "module": "Module A — Textual Conversations",
            "topics": ["Comparative Study of Texts", "Context and Reinterpretation"],
        },
        {
            "module": "Module B — Critical Study of Literature",
            "topics": ["Close Textual Analysis", "Authorial Intent and Reception"],
        },
        {
            "module": "Module C — The Craft of Writing",
            "topics": ["Imaginative Writing", "Discursive and Persuasive Writing", "Reflection Statements"],
        },
    ],
    "Software Engineering": [
        {
            "module": "Programming Fundamentals",
            "topics": ["Data Types and Structures", "Control Structures", "Functions and Procedures"],
        },
        {
            "module": "Developing Solutions by Creating and Modifying Software",
            "topics": ["Algorithms", "Debugging and Testing", "Software Development Approaches"],
        },
        {
            "module": "Programming for the Web",
            "topics": ["Client-Side vs Server-Side", "HTML/CSS/JS Fundamentals", "Web Architecture"],
        },
        {
            "module": "Software Automation Systems",
            "topics": ["Embedded Systems", "Control Systems and Sensors"],
        },
        {
            "module": "Secure Software Architecture",
            "topics": ["Cyber Security Concepts", "Authentication and Encryption", "Secure Design Principles"],
        },
    ],
    "General": [
        {
            "module": "Custom Topic",
            "topics": ["Let Dusty infer the topic from my description"],
        },
    ],
}


def get_subjects() -> list[str]:
    return list(SYLLABUS_TOPICS.keys())


def get_modules(subject: str) -> list[dict]:
    return SYLLABUS_TOPICS.get(subject, SYLLABUS_TOPICS["General"])