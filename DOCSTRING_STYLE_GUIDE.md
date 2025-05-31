# Meal Planner Docstring Style Guide

This project follows the Google docstring style for all public modules, classes, functions, and methods. All public APIs must have meaningful docstrings that go beyond merely restating the function/method signature.

## General Rules

1. **All public modules, classes, functions, and methods must have docstrings**
2. **Docstrings must be meaningful** - they should explain the purpose, behavior, and usage, not just restate the signature
3. **Use triple double quotes** for all docstrings: `"""`
4. **First line should be a concise summary** that fits on one line
5. **For multi-line docstrings**, leave a blank line after the summary before the rest of the docstring

## Module Docstrings

Every Python module should start with a docstring explaining its purpose:

```python
"""Brief one-line summary of the module.

This module provides functionality for [describe what the module does].
It includes [key features or components].
"""
```

## Class Docstrings

Classes should have docstrings that describe their purpose and usage:

```python
class Recipe:
    """Represents a cooking recipe with ingredients and instructions.
    
    This class stores recipe data including name, ingredients, and cooking
    instructions. It provides methods for formatting the recipe as markdown
    and other operations.
    
    Attributes:
        name: The name of the recipe.
        ingredients: List of ingredient strings.
        instructions: List of instruction steps.
    """
```

## Function/Method Docstrings

Functions and methods should follow the Google style with sections for Args, Returns, Raises, etc:

```python
def process_recipe(url: str, modifications: Optional[list[str]] = None) -> Recipe:
    """Extract and optionally modify a recipe from a given URL.
    
    Fetches the webpage content, extracts recipe information using LLM,
    and applies any requested modifications to the recipe.
    
    Args:
        url: The URL of the webpage containing the recipe.
        modifications: Optional list of modification requests to apply
            to the extracted recipe. If None, returns the recipe as-is.
    
    Returns:
        A Recipe object containing the extracted (and possibly modified)
        recipe data.
    
    Raises:
        HTTPError: If the webpage cannot be fetched.
        ValueError: If no valid recipe can be extracted from the page.
        LLMError: If the LLM service fails to process the recipe.
    
    Example:
        >>> recipe = await process_recipe("https://example.com/recipe")
        >>> print(recipe.name)
        "Chocolate Chip Cookies"
    """
```

## Property Docstrings

Properties should have docstrings that describe what they return:

```python
@property
def markdown(self) -> str:
    """Generate a markdown representation of the recipe.
    
    Returns a formatted string with recipe name, ingredients,
    and instructions in markdown format.
    """
```

## What Makes a Good Docstring?

### ❌ Bad Examples (just restating the obvious):

```python
def get_recipe(id: int) -> Recipe:
    """Gets a recipe by id."""  # Bad: adds no value
    
def set_name(self, name: str) -> None:
    """Sets the name."""  # Bad: obvious from signature
```

### ✅ Good Examples (adding context and value):

```python
def get_recipe(id: int) -> Recipe:
    """Retrieve a recipe from the database by its unique identifier.
    
    Args:
        id: The database primary key of the recipe to retrieve.
        
    Returns:
        The Recipe object if found.
        
    Raises:
        RecipeNotFoundError: If no recipe exists with the given id.
    """
    
def set_name(self, name: str) -> None:
    """Update the recipe name with validation.
    
    The name must be non-empty and will be stripped of leading/trailing
    whitespace. Updates are immediately persisted to the database.
    
    Args:
        name: The new recipe name. Must contain at least one 
            non-whitespace character.
            
    Raises:
        ValueError: If name is empty or contains only whitespace.
    """
```

## Special Cases

### Route Handlers

For FastAPI/FastHTML route handlers, focus on the API behavior:

```python
@app.get("/recipes/{recipe_id}")
async def get_recipe_endpoint(recipe_id: int) -> RecipeResponse:
    """Retrieve a single recipe by ID.
    
    Fetches the full recipe details including ingredients and instructions.
    Used by the recipe detail page and edit forms.
    
    Args:
        recipe_id: The unique identifier of the recipe.
        
    Returns:
        JSON response containing the recipe data.
        
    Raises:
        HTTPException: 404 if recipe not found, 500 for server errors.
    """
```

### Private Functions

Private functions (those starting with `_`) are encouraged but not required to have docstrings. However, complex private functions should still be documented for maintainability.

## Enforcement

This project uses `ruff` with docstring checking enabled (`"D"` rules) to enforce these standards. The configuration is in `pyproject.toml`:

- Google convention is enforced
- Tests, migrations, and scripts are exempt from docstring requirements
- Magic methods (`__init__`, `__str__`, etc.) don't require docstrings unless they have non-obvious behavior