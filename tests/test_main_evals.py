"""
LLM evals for main.py, rather than traditional unit tests.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from meal_planner.main import Recipe, extract_recipe_from_url

recipes = {
    Path("data/classic-deviled-eggs-recipe-1911032.html"): {
        "expected_names": ["Classic Deviled Eggs"],
        "expected_ingredients": [
            "6 eggs",
            "1/4 cup mayonnaise",
            "1 teaspoon white vinegar",
            "1 teaspoon yellow mustard",
            "1/8 teaspoon salt",
            "Freshly ground black pepper",
            "Smoked Spanish paprika, for garnish",
        ],
        "expected_instructions": [
            "Place eggs in a single layer in a saucepan and cover with enough water that there's 1 1/2 inches of water above the eggs. Heat on high until water begins to boil, then cover, turn the heat to low, and cook for 1 minute. Remove from heat and leave covered for 14 minutes, then rinse under cold water continuously for 1 minute.",
            "Crack egg shells and carefully peel under cool running water. Gently dry with paper towels. Slice the eggs in half lengthwise, removing yolks to a medium bowl, and placing the whites on a serving platter. Mash the yolks into a fine crumble using a fork. Add mayonnaise, vinegar, mustard, salt, and pepper, and mix well.",
            "Evenly disperse heaping teaspoons of the yolk mixture into the egg whites. Sprinkle with paprika and serve.",
        ],
    },
    Path("data/good-old-fashioned-pancakes.html"): {
        "expected_names": [
            "Good Old Fashioned Pancakes",
            "Good Old-Fashioned Pancakes",
            "Old-Fashioned Pancakes",
        ],
        "expected_ingredients": [
            "1 ½ cups all-purpose flour",
            "3 ½ teaspoons baking powder",
            "1 tablespoon white sugar",
            "¼ teaspoon salt, or more to taste",
            "1 ¼ cups milk",
            "3 tablespoons butter, melted",
            "1 large egg",
        ],
        "expected_instructions": [
            (
                "Sift flour, baking powder, sugar, and salt together in a large bowl. "
                "Make a well in the center and add milk, melted butter, and egg; "
                "mix until smooth."
            ),
            (
                "Heat a lightly oiled griddle or pan over medium-high heat. Pour or "
                "scoop the batter onto the griddle, using approximately 1/4 cup for "
                "each pancake; cook until bubbles form and the edges are dry, about "
                "2 to 3 minutes. Flip and cook until browned on the other side. "
                "Repeat with remaining batter."
            ),
        ],
    },
    Path("data/skillet-chicken-parmesan-with-gnocchi.html"): {
        "expected_names": ["Skillet Chicken Parmesan With Gnocchi"],
        "expected_ingredients": [
            "2 medium skinless, boneless chicken breasts (about 1 lb.), patted dry",
            "4¼ tsp. Diamond Crystal or 2½ tsp. Morton kosher salt, divided",
            "¼ cup all-purpose flour",
            "¼ cup (or more) extra-virgin olive oil",
            "8 garlic cloves, finely chopped",
            "½ tsp. crushed red pepper flakes",
            "1 28-oz. can whole peeled tomatoes",
            "1½ tsp. sugar",
            "1 17.5-oz. package shelf-stable potato gnocchi",
            "2 oz. Parmesan, finely grated",
            '8 oz. part-skim mozzarella, sliced ¼" thick',
            "Basil leaves (for serving; optional)",
        ],
        "expected_instructions": [
            (
                "Working with 1 breast at a time, hold a long knife parallel to "
                "cutting board and cut **2 medium skinless, boneless chicken breasts "
                "(about 1 lb.), patted dry**, in half, slicing along a long side to "
                "make thin cutlets. Arrange all 4 cutlets in an even layer on cutting "
                "board and sprinkle all over with **2 tsp. Diamond Crystal or 1¼ tsp. "
                "Morton kosher salt**. Transfer to a medium bowl and sprinkle with **¼ "
                "cup all-purpose flour**; toss to coat."
            ),
            (
                "Heat **¼ cup extra-virgin olive oil** in a large high-sided ovenproof "
                "skillet, preferably cast iron, over medium. Working in 2 batches and "
                "adding more oil between batches if needed, lift cutlets from bowl, "
                "shaking off excess flour, and carefully lower into skillet. Cook "
                "until deep golden brown, about 3 minutes per side (chicken will "
                "finish cooking in oven). Transfer to a large plate or baking sheet."
            ),
            (
                "Reduce heat to medium-low. Add **8 garlic cloves, finely chopped**, and "
                "**½ tsp. crushed red pepper flakes** to skillet and cook, stirring "
                "constantly, until fragrant, about 1 minute. Add **one 28-oz. can "
                "whole peeled tomatoes**, crushing with your hands as you go, then add "
                "remaining **2¼ tsp. Diamond Crystal or 1¼ tsp. Morton kosher salt** and "
                "**1½ tsp. sugar**. Bring to a simmer and cook, stirring occasionally, "
                "until sauce is slightly thickened, about 5 minutes. Add **one "
                "17.5-oz. package shelf-stable potato gnocchi** and cook, stirring "
                "constantly, until gnocchi is barely tender, about 2 minutes. Remove "
                "from heat."
            ),
            (
                "Heat broiler. Arrange chicken in a single layer over gnocchi. Top "
                "chicken with **2 oz. Parmesan, finely grated**, followed by **8 oz. "
                'part-skim mozzarella, sliced ¼** " **thick**. Transfer skillet to oven and '
                "broil until cheese is melted and browned, 5–8 minutes; watch closely "
                "to avoid burning."
            ),
            ("Serve chicken parm topped with **basil leaves** if desired."),
        ],
    },
    Path("data/gochujang-sloppy-joes.html"): {
        "expected_names": ["Gochujang Sloppy Joes"],
        "expected_ingredients": [
            "1 Tbsp. vegetable oil",
            "1 lb. ground beef (ideally 20% fat)",
            "1½ tsp. Diamond Crystal or ¾ tsp. Morton kosher salt, divided, plus more",
            "Freshly ground pepper",
            "1 medium green bell pepper, ribs and seeds removed, chopped",
            "1 medium onion, chopped",
            "6–8 garlic cloves, finely grated",
            "3 Tbsp. gochujang",
            "2 Tbsp. ketchup",
            "1 Tbsp. soy sauce",
            "1 Tbsp. Worcestershire sauce",
            "1 Tbsp. dark brown sugar",
            "1 tsp. yellow mustard",
            "1 15-oz. can tomato sauce",
            "1 Tbsp. balsamic vinegar",
            "4 potato rolls",
            "Kosher dill spears and potato chips (for serving; optional)",
        ],
        "expected_instructions": [
            (
                "Heat **1 Tbsp. vegetable oil** in a large skillet over medium-high. Add **1 lb. "
                "ground beef (ideally 20% fat)**, spreading out in a single "
                "layer; sprinkle with **1 tsp. Diamond Crystal or ½ tsp. "
                "Morton kosher salt** and season with **freshly ground pepper**. Cook, "
                "undisturbed, until a light brown crust forms underneath, about 3 "
                "minutes. Continue to cook, breaking up with a wooden spoon, until "
                "almost completely brown all the way through, about 3 minutes more."
            ),
            (
                "Push meat to one side of pan. Reduce heat to medium and add **1 "
                "medium green bell pepper, ribs and seeds removed, chopped**, **1 "
                "medium onion, chopped**, **6–8 garlic cloves, finely grated**, and "
                "**½ tsp. Diamond Crystal or ¼ tsp. Morton kosher salt**; season with "
                "pepper. Cook, stirring often, until vegetables are softened, about 5 "
                "minutes. Stir in **3 Tbsp. gochujang**, **2 Tbsp. ketchup**, **1 "
                "Tbsp. soy sauce**, **1 Tbsp. Worcestershire sauce**, **1 Tbsp. dark "
                "brown sugar**, and **1 tsp. yellow mustard**, then add **one 15-oz. "
                "can tomato sauce** and ¼ cup water and stir again to combine. Bring "
                "to a simmer and reduce heat to medium-low. Cook, stirring and "
                "scraping up any brown bits, until thick and saucy, 10–12 minutes. "
                "Remove beef mixture from heat and stir in **1 Tbsp. balsamic "
                "vinegar**; season with salt and pepper."
            ),
            (
                "Spoon beef mixture onto **4 potato rolls**. Serve with **kosher dill "
                "spears** and **potato chips** if desired."
            ),
        ],
    },
    Path("data/mushroom-pasta-creamy.html"): {
        "expected_names": [
            "Pasta Ai Funghi",
            "Pasta Ai Funghi (Creamy Pasta With Mushrooms)",
            "Creamy Pasta With Mushrooms",
        ],
        "expected_ingredients": [
            "1 cup (240 ml) homemade or store-bought low-sodium chicken stock (see "
            "note)",
            "1 1/2 teaspoons (4 g) powdered gelatin, such as Knox",
            "2 tablespoons (30 ml) extra-virgin olive oil",
            "1 1/2 pounds (675 g) mixed mushrooms (such as shiitake, oyster, maitake, "
            "beech, cremini, and chanterelles), cleaned, trimmed, and thinly sliced or "
            "torn by hand (see note)",
            "Kosher salt and freshly ground black pepper",
            "3 medium shallots, finely minced (about 3/4 cup; 120 g)",
            "2 medium (10 g) garlic cloves, minced",
            "2 tablespoons (4 g) chopped fresh thyme leaves",
            "1/2 cup (120 ml) dry white wine or 1/4 cup (60 ml) dry sherry",
            "1 pound (450 g) short dried pasta (such as casarecce or gemelli) or long "
            "fresh egg-dough pasta (such as tagliatelle or fettuccine)",
            "6 tablespoons unsalted butter (3 ounces; 85 g)",
            "3 ounces grated Parmigiano-Reggiano (1 cup; 85 g)",
            "1/4 cup (10 g) chopped fresh flat-leaf parsley leaves",
            "1 teaspoon (5 ml) fish sauce (optional)",
        ],
        "expected_instructions": [
            (
                "Pour stock into a small bowl or liquid measuring cup and evenly "
                "sprinkle gelatin over surface of stock. Set aside."
            ),
            (
                "In a large 12-inch cast iron or stainless steel skillet, heat oil "
                "over medium-high heat until shimmering. Add mushrooms, season with "
                "salt and pepper, and cook, stirring frequently with a wooden spoon, "
                "until moisture has evaporated and mushrooms are deeply browned, 12 to "
                "15 minutes."
            ),
            (
                "Add shallots, garlic, and thyme and cook, stirring constantly, until "
                "fragrant and shallots are softened, 30 seconds to 1 minute. Add wine "
                "or sherry, and cook, swirling pan and scraping up any stuck-on bits "
                "with a wooden spoon, until wine is reduced by half, about 30 "
                "seconds."
            ),
            (
                "Add chicken stock mixture, season lightly with salt, and bring to a "
                "simmer. Reduce heat to medium-low, add fish sauce (if using), and "
                "cook, stirring occasionally, until mushroom mixture is thickened to a "
                "saucy consistency, about 5 minutes. Turn off heat."
            ),
            (
                "Meanwhile, in a pot of salted boiling water, cook pasta. If using "
                "dry pasta, cook until just shy of al dente (1 to 2 minutes less than "
                "the package directs). If using fresh pasta, cook until noodles are "
                "barely cooked through. Using either a spider skimmer (for short "
                "pasta) or tongs (for long fresh pasta), transfer pasta to pan with "
                "mushrooms along with 3/4 cup (180ml) pasta cooking water. "
                "Alternatively, drain pasta using a colander or fine-mesh strainer, "
                "making sure to reserve at least 2 cups (475ml) pasta cooking water."
            ),
            (
                "Heat sauce and pasta over high and cook, stirring and tossing "
                "rapidly, until pasta is al dente (fresh pasta will never be truly "
                "al dente) and sauce is thickened and coats noodles, 1 to 2 minutes, "
                "adding more pasta cooking water in 1/4 cup (60ml) increments as "
                "needed. At this point, the sauce should coat the pasta but still be "
                "loose enough to pool around the edges of the pan. Add butter, and "
                "stir and toss rapidly to melt and emulsify into the sauce. Remove "
                "from heat, add 3/4 of grated cheese and all of the parsley, and stir "
                "rapidly to incorporate. Season with salt to taste. Serve "
                "immediately, passing remaining grated cheese at the table."
            ),
        ],
    },
    Path("data/easy-bok-choy-recipe_.html"): {
        "expected_names": ["Easy Bok Choy", "Bok Choy"],
        "expected_ingredients": [
            "3 Tbsp. vegetable oil, divided",
            "1 lb. baby bok choy, quartered lengthwise, washed, dried",
            "2 garlic cloves, finely chopped",
            '1 (1") piece ginger, peeled, finely chopped',
            "1 tsp. kosher salt, divided",
            "1 Tbsp. reduced-sodium soy sauce",
            "1/2 tsp. toasted sesame oil",
        ],
        "expected_instructions": [
            (
                "In a large skillet over medium-high heat, heat 1 Tbsp. vegetable "
                "oil. Add half of bok choy, arranging cut side down in a single layer, "
                "and cook, undisturbed, until golden brown, 3 to 4 minutes. Transfer "
                "to a plate. Repeat with 1 Tbsp. vegetable oil and remaining bok choy."
            ),
            (
                "Reduce heat to medium. In same skillet, heat remaining 1 Tbsp. "
                "vegetable oil. Add garlic and ginger and cook, stirring, until "
                "fragrant, 30 to 60 seconds. Return bok choy to pan; season with 1/2 "
                "tsp. salt and toss to combine."
            ),
            (
                "Add soy sauce and 1 Tbsp. water. Cover and steam until bok choy is "
                "just fork-tender, 2 to 4 minutes. Uncover and continue to cook, "
                "tossing frequently, until liquid is evaporated, about 30 seconds more; "
                "season with remaining 1/2 tsp. salt, if needed."
            ),
            ("Transfer bok choy to a platter. Drizzle with sesame oil."),
        ],
    },
    Path("data/sunshine-sauce-recipe-23706247.html"): {
        "expected_names": ["Sunshine Sauce"],
        "expected_ingredients": [
            "1 teaspoon finely grated lemon zest",
            "1 tablespoon plus 1 teaspoon freshly squeezed lemon juice",
            "1 tablespoon water",
            "8 tablespoons (1 stick) cold unsalted butter, preferably European-style "
            "such as Kerrygold, cut into 8 pieces",
            "1 tablespoon coarsely chopped fresh parsley leaves (from about 3 sprigs)",
            "1 clove garlic, minced",
            "1/4 teaspoon kosher salt, plus more as needed",
            "1/4 teaspoon freshly ground black pepper, plus more as needed",
        ],
        "expected_instructions": [
            (
                "Bring 1 tablespoon plus 1 teaspoon lemon juice and 1 tablespoon water "
                "to a simmer in a small skillet or saucepan over medium-low heat. "
                "Reduce the heat to low. Whisk in 1 stick cold unsalted butter a "
                "tablespoon at a time, whisking until each piece is almost melted "
                "before adding the next. Do not let the butter boil, or it will "
                "separate."
            ),
            (
                "Whisk in 1 teaspoon finely grated lemon zest, 1 tablespoon coarsely "
                "chopped fresh parsley leaves, 1 minced garlic clove, 1/4 teaspoon "
                "kosher salt, and 1/4 teaspoon black pepper. Taste and season with "
                "more kosher salt or black pepper as needed. Serve warm."
            ),
        ],
    },
    Path("data/quick-healthy-dinner-20-minute-honey-garlic-shrimp_.html"): {
        "expected_names": ["20 Minute Honey Garlic Shrimp", "Honey Garlic Shrimp"],
        "expected_ingredients": [
            "1/3 cup honey",
            "1/4 cup soy sauce (we usually use reduced sodium)",
            "2 garlic cloves, minced (or 1 teaspoon jarred minced garlic)",
            "1 lb medium uncooked shrimp, peeled & deveined",
            "2 teaspoons olive oil",
            "optional: 1 teaspoon minced fresh ginger",
            "optional for garnish: chopped green onion",
        ],
        "expected_instructions": [
            "Whisk the honey, soy sauce, garlic, and ginger (if using) together in a medium bowl. You will use half for the marinade in step 2 and half for cooking the shrimp in step 3.",
            "Place shrimp in a large sealable container or zipped-top bag. Pour 1/2 of the marinade/sauce mixture on top, give it all a shake or stir, then allow shrimp to marinate in the refrigerator for 15 minutes or for up to 8-12 hours. Cover and refrigerate the rest of the marinade for step 3. (Time-saving tip: while the shrimp is marinating, we usually steam broccoli and microwave some quick brown rice.)",
            "Heat olive oil in a skillet over medium-high heat. Place shrimp in the skillet. (Discard used marinade.) Cook shrimp on one side until pink, about 45 seconds, then flip shrimp over. Pour in remaining marinade/sauce and cook it all until shrimp is cooked through, about 1-2 more minutes.",
            "Serve shrimp with cooked marinade sauce and a garnish of green onion. The sauce is excellent on brown rice and steamed vegetables on the side.",
        ],
    },
    Path("data/prawn-salmon-burgers-spicy-mayo.html"): {
        "expected_names": ["Prawn & Salmon Burgers With Spicy Mayo"],
        "expected_ingredients": [
            "180g pack peeled raw prawns roughly chopped",
            "4 skinless salmon fillets, chopped into small chunks",
            "3 spring onions roughly chopped",
            "1 lemon zested and juiced",
            "small pack coriander",
            "60g mayonnaise or Greek yogurt",
            "4 tsp chilli sauce (we used sriracha)",
            "2 Little Gem lettuces shredded",
            "1 cucumber peeled into ribbons",
            "1 tbsp olive oil",
            "4 seeded burger buns toasted, to serve",
        ],
        "expected_instructions": [
            "Briefly blitz half the prawns, half the salmon, the spring onions, lemon zest and half the coriander in a food processor until it forms a coarse paste. Tip into a bowl, stir in the rest of the prawns and salmon, season well and shape into four burgers. Chill for 10 mins.",
            "Mix the mayo and chilli sauce together in a small bowl, season and add some lemon juice to taste. Mix the lettuce with the cucumber, dress with a little of the remaining lemon juice and 1 tsp olive oil, then set aside.",
            "Heat the remaining oil in a large frying pan and fry the burgers for 3-4 mins each side or until they have a nice crust and the fish is cooked through. Serve with the salad on the side or in toasted burger buns, if you like, with a good dollop of the spicy mayo.",
        ],
    },
    Path("data/easy-homemade-falafel-recipe_.html"): {
        "expected_names": ["Easy Homemade Falafel", "Homemade Falafel"],
        "expected_ingredients": [
            "1 cup dried chickpeas",
            "1/2 small white onion, coarsely chopped",
            "4 garlic cloves, coarsely chopped",
            "1/4 cup fresh cilantro, coarsely chopped",
            "1/4 cup fresh parsley, coarsely chopped",
            "1 1/2 tsp. kosher salt",
            "1 tsp. baking powder",
            "1 tsp. ground coriander",
            "1 tsp. ground cumin",
            "1/4 cup all-purpose flour",
            "Vegetable oil, for frying (6 to 8 cups)",
            "Tahini sauce, for serving",
        ],
        "expected_instructions": [
            'In a large bowl, cover chickpeas with cold water by at least 2". Cover and refrigerate overnight.',
            "Drain chickpeas well, pat dry, and transfer to a food processor. Pulse until chickpeas are halfway broken down. Add onion, garlic, cilantro, parsley, salt, baking powder, coriander, and cumin and continue to pulse until finely chopped but not pasty. Sprinkle flour over and pulse just until combined.",
            'Using a 1-oz. cookie scoop or 2 spoons, portion chickpea mixture into 1" balls (about 2 Tbsp. each). Using clean hands, roll each ball, tossing between both hands and lightly squeezing to compress, until smooth and compact (mixture will feel wet). Arrange balls on a clean plate or parchment-lined baking sheet.',
            'Into a large heavy pot fitted with a deep-fry or candy thermometer, pour oil to a depth of 2". Heat over high heat until thermometer registers 350°. Set a wire rack in a large baking sheet. Working 6 to 7 at a time, gently lower falafel into oil and fry, adjusting heat as needed, until deeply browned on all sides, 2 to 3 minutes.',
            "Remove from oil with a slotted spoon and transfer to prepared rack to cool. Serve warm with tahini sauce alongside.",
        ],
    },
}


@pytest.fixture(
    params=recipes.keys(), ids=[str(p.name) for p in recipes], scope="module"
)
@patch("meal_planner.main.fetch_page_text")
async def extracted_recipe_fixture(mock_fetch, request, anyio_backend):
    """Fixture to extract recipe data for a given path."""
    path: Path = request.param
    raw_text = (Path(__file__).resolve().parent / path).read_text()
    mock_fetch.return_value = raw_text

    extracted_recipe = await extract_recipe_from_url("http://dummy-url.com")
    return extracted_recipe, path


@pytest.mark.slow
@pytest.mark.anyio
def test_extract_recipe_name(extracted_recipe_fixture):
    """Tests the extracted recipe name against expected values."""
    extracted_recipe: Recipe
    path: Path
    extracted_recipe, path = extracted_recipe_fixture

    expected_names_list = recipes[path]["expected_names"]
    actual_name = extracted_recipe.name

    assert actual_name in expected_names_list


@pytest.mark.slow
@pytest.mark.anyio
def test_extract_recipe_ingredients(extracted_recipe_fixture):
    """Tests the extracted recipe ingredients against expected values."""
    extracted_recipe: Recipe
    path: Path
    extracted_recipe, path = extracted_recipe_fixture

    expected = sorted([i.lower() for i in recipes[path]["expected_ingredients"]])
    actual = sorted([i.lower() for i in extracted_recipe.ingredients])
    assert actual == expected


@pytest.mark.slow
@pytest.mark.anyio
def test_extract_recipe_instructions(extracted_recipe_fixture):
    """Tests the extracted recipe instructions against expected values."""
    extracted_recipe: Recipe
    path: Path
    extracted_recipe, path = extracted_recipe_fixture

    expected_instructions = recipes[path]["expected_instructions"]
    actual_instructions = extracted_recipe.instructions
    assert actual_instructions == expected_instructions
