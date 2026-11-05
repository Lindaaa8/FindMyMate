"""Options, new-user defaults, and the sample (seeded) accounts for FindYourMate."""

GENDER_PREF_OPTIONS = ["Male", "Female", "Transgender", "Non-binary", "Other"]
MARRIAGE_STATUS_OPTIONS = ["Single", "Dating", "In Relationship"]

# Connection finite-state machine:
# RECOMMENDED -> FAVOURED (they liked you) / INVITED (you liked them) -> CHATTING -> DATING -> CLOSED
STATES = ["RECOMMENDED", "FAVOURED", "INVITED", "CHATTING", "DATING", "CLOSED"]
ACTIVE_STATES = {"FAVOURED", "INVITED", "CHATTING", "DATING"}

CHAT_COMMITMENT_MS = 72 * 60 * 60 * 1000  # 72h to decide after chat starts

IDEAL_TEXT_FIELDS = ["education", "ethnicity", "occupation", "skinColor", "height", "location", "notWant"]
PROFILE_TEXT_FIELDS = ["name", "bio", "education", "age", "ethnicity", "nationality", "faith", "career",
                       "location", "height", "hobbies", "hometown", "mbti"]

# Starting profile for a newly registered user; they fill it in through the Edit dialogs.
NEW_PROFILE = {
    "name": "",
    "photos": [None] * 9,
    "bio": "",
    "education": "",
    "age": "",
    "ethnicity": "",
    "nationality": "",
    "faith": "",
    "career": "",
    "location": "",
    "height": "",
    "hobbies": "",
    "hometown": "",
    "mbti": "",
    "gender": "",
    "ideal": {
        "education": "",
        "ethnicity": "",
        "occupation": "",
        "skinColor": "",
        "height": "",
        "location": "",
        "notWant": "",
        "mbti": "",
        "age": "",
        "otherRequirement": "",
        "genderPreference": "",
    },
    "photoVerified": False,
    "marriageStatus": "Single",
    "marriageVerified": False,
    "saved": False,
    "confirmed": False,
}

CANDIDATES = [
    {
        "id": "c1", "name": "Maya", "age": 27, "gender": "Female",
        "education": "MSc Computer Science, MIT", "ethnicity": "East Asian", "nationality": "American",
        "faith": "Agnostic", "career": "Product Designer", "location": "San Francisco, CA", "height": "5'6",
        "bio": "Weekend climber, weekday builder. I love quiet mornings, good coffee, and museums that make me linger. "
               "Looking for someone who values depth and curiosity over display. I spend Sundays at the bouldering gym "
               "and evenings cooking experiments that sometimes work.",
        "hobbies": "Climbing, Film photography, Indie coffee", "hometown": "Seattle",
        "photoVerified": True, "marriageStatus": "Single", "marriageVerified": True,
        "skin": "Light", "mbti": "INFJ", "color": "#a78bfa", "matchScore": 96, "photoCount": 4,
        "ideal": {"education": "Masters+", "occupation": "Tech/Design", "location": "West Coast", "genderPreference": "Female", "age": "25-32"},
    },
    {
        "id": "c2", "name": "Sofia", "age": 26, "gender": "Female",
        "education": "BA Literature, NYU", "ethnicity": "Hispanic", "nationality": "Spanish",
        "faith": "Catholic", "career": "Editor", "location": "Austin, TX", "height": "5'5",
        "bio": "Bookstore regular. Writing a novel slowly. Looking for someone who values depth over display. "
               "I collect vinyl and dog-ear poetry books. If you can recommend a quiet bar with good whiskey, "
               "we will get along.",
        "hobbies": "Writing, Vinyl, Poetry", "hometown": "Madrid",
        "photoVerified": False, "marriageStatus": "Single", "marriageVerified": False,
        "skin": "Medium", "mbti": "INFP", "color": "#f472b6", "matchScore": 91, "photoCount": 3,
        "ideal": {"education": "BA+", "occupation": "Creative", "location": "Open", "genderPreference": "Female", "age": "24-30"},
    },
    {
        "id": "c3", "name": "Aisha", "age": 29, "gender": "Female",
        "education": "PhD Medicine, Imperial", "ethnicity": "South Asian", "nationality": "British",
        "faith": "Muslim", "career": "Doctor", "location": "London, UK", "height": "5'7",
        "bio": "Curious, grounded, ambitious. Family-oriented, but independent. I value honesty above all. "
               "I travel for medical missions and come home to a very spoiled cat. Looking for a partner who is "
               "kind, consistent, and ready.",
        "hobbies": "Cooking, Travel, Medicine", "hometown": "Birmingham",
        "photoVerified": True, "marriageStatus": "Single", "marriageVerified": True,
        "skin": "Brown", "mbti": "ENFJ", "color": "#facc15", "matchScore": 88, "photoCount": 5,
        "ideal": {"education": "MD/PhD", "occupation": "Professional", "location": "London / Remote", "genderPreference": "Male", "age": "28-36"},
    },
    {
        "id": "c4", "name": "Emma", "age": 28, "gender": "Female",
        "education": "MBA, Wharton", "ethnicity": "Caucasian", "nationality": "American",
        "faith": "Christian", "career": "Consultant", "location": "New York, NY", "height": "5'8",
        "bio": "NYC transplant. Love long runs along the river and second-hand bookshops. Looking for partner to "
               "grow with. My ideal weekend: run, farmer market, lazy reading. I talk fast but listen better.",
        "hobbies": "Running, Reading, Markets", "hometown": "Boston",
        "photoVerified": True, "marriageStatus": "Single", "marriageVerified": True,
        "skin": "Light", "mbti": "ESTJ", "color": "#60a5fa", "matchScore": 84, "photoCount": 3,
        "ideal": {"education": "Masters", "occupation": "Consultant / Finance", "location": "NYC", "genderPreference": "Female", "age": "26-34"},
    },
    {
        "id": "c5", "name": "Kenji", "age": 30, "gender": "Male",
        "education": "BSc Architecture, Kyoto U", "ethnicity": "East Asian", "nationality": "Japanese",
        "faith": "Buddhist", "career": "Architect", "location": "Portland, OR", "height": "6'0",
        "bio": "Minimalist at heart. I design spaces that breathe. Searching for calm, mutual respect, and laughter. "
               "I make my own tea blends and my apartment smells like cedar.",
        "hobbies": "Architecture, Tea, Woodworking", "hometown": "Kyoto",
        "photoVerified": True, "marriageStatus": "Single", "marriageVerified": True,
        "skin": "Light", "mbti": "INTJ", "color": "#34d399", "matchScore": 79, "photoCount": 2,
        "ideal": {"education": "BSc+", "occupation": "Design", "location": "West Coast", "genderPreference": "Female", "age": "25-33"},
    },
    {
        "id": "c6", "name": "Zara", "age": 26, "gender": "Non-binary",
        "education": "MSc Economics, Toronto", "ethnicity": "Middle Eastern", "nationality": "Canadian",
        "faith": "Agnostic", "career": "Analyst", "location": "Toronto, CA", "height": "5'6",
        "bio": "Analytical but romantic. Love data and poetry in equal measure. Let’s be curious together. "
               "I am learning chess and losing gracefully.",
        "hobbies": "Poetry, Chess, Hiking", "hometown": "Vancouver",
        "photoVerified": True, "marriageStatus": "Single", "marriageVerified": True,
        "skin": "Olive", "mbti": "ENTP", "color": "#fb7185", "matchScore": 76, "photoCount": 4,
        "ideal": {"education": "Masters", "occupation": "Analyst / Creative", "location": "Canada", "genderPreference": "Female", "age": "24-32"},
    },
]

AUTO_REPLIES = [
    "That resonates with me. Tell me more about {hobby}?",
    "I loved your bio. Quiet mornings and museums sound perfect.",
    "What's your ideal Sunday like?",
    "I appreciate your honesty about what you value.",
]
