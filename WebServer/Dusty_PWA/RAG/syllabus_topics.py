"""
RAG/syllabus_topics.py — NSW HSC syllabus topic reference

Used by the Quiz Generator modal so students pick an actual syllabus
topic *name* instead of typing an ambiguous module code.

All mathematical notation uses Unicode (θ π ² √ etc.) so Gemini
never needs LaTeX backslashes inside JSON strings.
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
                "Models of the Atom",
                "Properties of the Nucleus",
                "Deep Inside the Nucleus",
                "Origins of the Elements",
            ],
        },
    ],

    "Chemistry": [
        {
            "module": "Module 5 — Equilibrium and Acid Reactions",
            "topics": [
                "Static and Dynamic Equilibrium",
                "Factors Affecting Equilibrium",
                "Quantitative Analysis",
            ],
        },
        {
            "module": "Module 6 — Acid/Base Reactions",
            "topics": [
                "Properties of Acids and Bases",
                "Brønsted-Lowry Theory",
                "Quantitative Analysis of Acids and Bases",
            ],
        },
        {
            "module": "Module 7 — Organic Chemistry",
            "topics": [
                "Nomenclature",
                "Hydrocarbons",
                "Reactions of Organic Molecules",
                "Polymers",
            ],
        },
        {
            "module": "Module 8 — Applying Chemical Ideas",
            "topics": [
                "Analysis of Inorganic Substances",
                "Analysis of Organic Substances",
                "Chemical Synthesis and Design",
            ],
        },
    ],

    "Biology": [
        {
            "module": "Module 5 — Heredity",
            "topics": [
                "Reproduction",
                "Cell Replication",
                "DNA and Polypeptide Synthesis",
                "Inheritance Patterns in a Population",
            ],
        },
        {
            "module": "Module 6 — Genetic Change",
            "topics": [
                "Mutation",
                "Biotechnology",
                "Genetic Technologies",
            ],
        },
        {
            "module": "Module 7 — Infectious Disease",
            "topics": [
                "Causes of Infectious Disease",
                "Transmission of Disease",
                "Defending Against Infectious Disease",
            ],
        },
        {
            "module": "Module 8 — Non-Infectious Disease and Disorders",
            "topics": [
                "Homeostasis",
                "Causes and Effects of Non-Infectious Disease",
                "Epidemiology",
            ],
        },
    ],

    "Mathematics Advanced": [
        {
            "module": "Functions",
            "topics": [
                "Working with Functions",
                "Polynomials",
                "Other Graphs and Relationships",
            ],
        },
        {
            "module": "Trigonometric Functions",
            "topics": [
                "Trigonometric Functions and Identities",
                "Trigonometric Equations",
                "Graphs of Trigonometric Functions",
            ],
        },
        {
            "module": "Calculus",
            "topics": [
                "Differentiation",
                "Applications of Differentiation",
                "Integration",
            ],
        },
        {
            "module": "Exponential and Logarithmic Functions",
            "topics": [
                "Exponential and Logarithmic Laws",
                "Growth and Decay Applications",
            ],
        },
        {
            "module": "Statistical Analysis",
            "topics": [
                "Discrete Probability Distributions",
                "The Normal Distribution",
                "Bivariate Data Analysis",
            ],
        },
        {
            "module": "Financial Mathematics",
            "topics": [
                "Compound Interest and Depreciation",
                "Annuities and Loan Repayments",
            ],
        },
    ],

    "Mathematics Extension 1": [
        {
            "module": "Functions",
            "topics": [
                "Inverse Functions",
                "Parametric Forms of a Function",
                "Further Work with Functions",
            ],
        },
        {
            "module": "Trigonometric Functions",
            "topics": [
                "Inverse Trigonometric Functions",
                "Further Trigonometric Identities",
                "t-formula and Half-Angle Substitution",
            ],
        },
        {
            "module": "Calculus",
            "topics": [
                "Integration by Substitution",
                "Integration of Trigonometric Functions",
                "Differential Equations",
                "Volumes of Solids of Revolution",
            ],
        },
        {
            "module": "Combinatorics",
            "topics": [
                "Permutations and Combinations",
                "Binomial Theorem",
                "Pigeonhole Principle",
            ],
        },
        {
            "module": "Proof",
            "topics": [
                "Mathematical Induction",
            ],
        },
        {
            "module": "Vectors",
            "topics": [
                "Introduction to Vectors",
                "Vector Equation of a Line",
                "Applications of Vectors in Two Dimensions",
            ],
        },
    ],

    "Mathematics Extension 2": [
        {
            "module": "Proof",
            "topics": [
                "The Nature of Proof",
                "Further Proof by Mathematical Induction",
            ],
        },
        {
            "module": "Vectors",
            "topics": [
                "Vectors in Three Dimensions",
                "Vector Equation of a Curve",
            ],
        },
        {
            "module": "Complex Numbers",
            "topics": [
                "Introduction to Complex Numbers",
                "De Moivre's Theorem and Applications",
                "Roots of Complex Numbers",
            ],
        },
        {
            "module": "Calculus",
            "topics": [
                "Integration Techniques",
                "Mechanics",
            ],
        },
    ],

    "Mathematics Standard 2": [
        {
            "module": "Algebra",
            "topics": [
                "Formula Applications",
                "Linear Equations and Inequalities",
                "Simultaneous Equations",
            ],
        },
        {
            "module": "Measurement",
            "topics": [
                "Rates and Ratios",
                "Scale Drawing and Similarity",
                "Right-Angled Triangle Trigonometry",
                "Non-Right-Angled Trigonometry",
            ],
        },
        {
            "module": "Financial Mathematics",
            "topics": [
                "Money and Financial Transactions",
                "Simple and Compound Interest",
                "Investments, Loans and Annuities",
            ],
        },
        {
            "module": "Statistical Analysis",
            "topics": [
                "Classifying and Representing Data",
                "Summary Statistics",
                "The Normal Distribution",
                "Bivariate Data Analysis",
            ],
        },
        {
            "module": "Networks",
            "topics": [
                "Network Concepts",
                "Critical Path Analysis",
            ],
        },
    ],

    "English Advanced": [
        {
            "module": "Common Module — Texts and Human Experiences",
            "topics": [
                "Prescribed Text Analysis",
                "Related Texts and Personal Experience",
            ],
        },
        {
            "module": "Module A — Textual Conversations",
            "topics": [
                "Comparative Study of Texts",
                "Context and Reinterpretation",
            ],
        },
        {
            "module": "Module B — Critical Study of Literature",
            "topics": [
                "Close Textual Analysis",
                "Authorial Intent and Reception",
            ],
        },
        {
            "module": "Module C — The Craft of Writing",
            "topics": [
                "Imaginative Writing",
                "Discursive and Persuasive Writing",
                "Reflection Statements",
            ],
        },
    ],

    "Software Engineering": [
        {
            "module": "Programming Fundamentals",
            "topics": [
                "Data Types and Structures",
                "Control Structures",
                "Functions and Procedures",
            ],
        },
        {
            "module": "Developing Solutions by Creating and Modifying Software",
            "topics": [
                "Algorithms",
                "Debugging and Testing",
                "Software Development Approaches",
            ],
        },
        {
            "module": "Programming for the Web",
            "topics": [
                "Client-Side vs Server-Side",
                "HTML/CSS/JS Fundamentals",
                "Web Architecture",
            ],
        },
        {
            "module": "Software Automation Systems",
            "topics": [
                "Embedded Systems",
                "Control Systems and Sensors",
            ],
        },
        {
            "module": "Secure Software Architecture",
            "topics": [
                "Cyber Security Concepts",
                "Authentication and Encryption",
                "Secure Design Principles",
            ],
        },
    ],

    "Modern History": [
        {
            "module": "Power and Authority in the Modern World 1919–1946",
            "topics": [
                "Versailles and the Peace Settlement",
                "Rise of Authoritarian States",
                "Causes and Course of World War II",
            ],
        },
        {
            "module": "National Studies",
            "topics": [
                "Germany 1919–1945",
                "Russia/USSR 1917–1941",
                "China 1935–1976",
                "Japan 1931–1951",
            ],
        },
        {
            "module": "Peace and Conflict",
            "topics": [
                "The Cold War 1945–1991",
                "The Korean War",
                "The Vietnam War",
                "The Arab-Israeli Conflict",
            ],
        },
        {
            "module": "Rights and Freedoms",
            "topics": [
                "Civil Rights Movement USA",
                "Apartheid in South Africa",
                "Aboriginal and Torres Strait Islander Rights",
            ],
        },
    ],

    "Ancient History": [
        {
            "module": "Investigating the Ancient Past",
            "topics": [
                "Nature and Reliability of Sources",
                "Historical Methodology",
                "Historiography",
            ],
        },
        {
            "module": "Personalities in Their Times",
            "topics": [
                "Hatshepsut",
                "Ramesses II",
                "Pericles",
                "Julius Caesar",
                "Augustus",
                "Agrippina",
                "Boudicca",
            ],
        },
        {
            "module": "Features of Ancient Societies",
            "topics": [
                "Egypt",
                "Greece",
                "Rome",
                "Pompeii and Herculaneum",
                "Sparta",
                "Persia",
            ],
        },
    ],

    "Legal Studies": [
        {
            "module": "The Legal System",
            "topics": [
                "Nature and Sources of Law",
                "Classification of Law",
                "The Australian Legal System",
                "International Law",
            ],
        },
        {
            "module": "The Individual and the Law",
            "topics": [
                "Consumers and the Law",
                "Global Environmental Protection",
                "Family Law",
                "Workplace Law",
            ],
        },
        {
            "module": "Law in Practice",
            "topics": [
                "Crime",
                "Human Rights",
                "World Order",
                "Indigenous Peoples",
            ],
        },
    ],

    "Economics": [
        {
            "module": "Introduction to Economics",
            "topics": [
                "The Economic Problem",
                "Markets",
                "Government and the Economy",
            ],
        },
        {
            "module": "Australia's Place in the Global Economy",
            "topics": [
                "Trade and Protection",
                "Balance of Payments",
                "Exchange Rates",
                "Economic Integration",
            ],
        },
        {
            "module": "Economic Issues",
            "topics": [
                "Employment and Unemployment",
                "Inflation",
                "Distribution of Income and Wealth",
                "Environmental Sustainability",
                "Economic Growth",
            ],
        },
        {
            "module": "Economic Policies",
            "topics": [
                "Fiscal Policy",
                "Monetary Policy",
                "Microeconomic Reform",
            ],
        },
    ],

    "Business Studies": [
        {
            "module": "Nature of Business",
            "topics": [
                "Role of Business",
                "Types of Business",
                "Business Lifecycle",
                "External Influences on Business",
            ],
        },
        {
            "module": "Business Management",
            "topics": [
                "Management Approaches",
                "Management and Change",
                "HR Management",
            ],
        },
        {
            "module": "Business Planning",
            "topics": [
                "Role of Business Planning",
                "Financial Planning",
                "Marketing Planning",
            ],
        },
        {
            "module": "Marketing",
            "topics": [
                "Role of Marketing",
                "Market Research",
                "Marketing Mix",
                "Marketing Strategies",
            ],
        },
        {
            "module": "Finance",
            "topics": [
                "Role of Financial Management",
                "Financial Planning and Budgeting",
                "Financial Reports and Analysis",
                "Working Capital Management",
            ],
        },
    ],
}

# Fuzzy-match aliases: maps lowercase keywords to canonical keys
# Used by the API when an exact match is not found
_SUBJECT_ALIASES: dict[str, str] = {
    "extension 1": "Mathematics Extension 1",
    "extension 2": "Mathematics Extension 2",
    "ext 1": "Mathematics Extension 1",
    "ext 2": "Mathematics Extension 2",
    "ext1": "Mathematics Extension 1",
    "ext2": "Mathematics Extension 2",
    "standard": "Mathematics Standard 2",
    "std": "Mathematics Standard 2",
    "advanced math": "Mathematics Advanced",
    "maths advanced": "Mathematics Advanced",
    "english": "English Advanced",
    "eng advanced": "English Advanced",
    "software": "Software Engineering",
    "sdd": "Software Engineering",
    "bio": "Biology",
    "chem": "Chemistry",
    "phys": "Physics",
    "modern": "Modern History",
    "ancient": "Ancient History",
    "legal": "Legal Studies",
    "econ": "Economics",
    "business": "Business Studies",
}


def get_subjects() -> list[str]:
    return list(SYLLABUS_TOPICS.keys())


def get_modules(subject: str) -> list[dict]:
    return SYLLABUS_TOPICS.get(subject, [])


def find_best_match(subject: str) -> str | None:
    """
    Given a subject name that may not exactly match a SYLLABUS_TOPICS key,
    find the best matching key using alias lookup then word-overlap scoring.
    Returns None if no reasonable match is found.
    """
    if not subject:
        return None

    # 1. Exact match
    if subject in SYLLABUS_TOPICS:
        return subject

    s = subject.lower().strip()

    # 2. Alias lookup
    for alias, canonical in _SUBJECT_ALIASES.items():
        if alias in s:
            return canonical

    # 3. Word-overlap scoring (ignore "General")
    subject_words = set(s.split())
    best_key, best_score = None, 0
    for key in SYLLABUS_TOPICS:
        if key == "General":
            continue
        overlap = len(subject_words & set(key.lower().split()))
        if overlap > best_score:
            best_score, best_key = overlap, key

    return best_key if best_score > 0 else None