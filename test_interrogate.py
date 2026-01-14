import json
import base64
import urllib.request
from pathlib import Path

def test_interrogate():
    still_path = Path("/home/gregm/hardware_exercises/picker/assets/latest_still.png")
    if not still_path.exists():
        print(f"Error: {still_path} not found.")
        return

    with open(still_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode('utf-8')

    # Values from sample_texts.json
    categories = {
        "Sex/Gender": ["Agender", "Bigender", "Cisgender", "Female", "Genderqueer", "Intersex", "Male", "Non-binary", "Transgender Man", "Transgender Woman", "Two-spirit"],
        "Age": ["Young Adult", "Adult", "Middle-aged", "Senior", "Elderly", "Retired", "Mature", "Midlife", "Wise", "Golden Years", "Venerable"],
        "Socioeconomics": ["Lower Class", "Working Class", "Middle Class", "Underclass", "Upper Class", "Wealthy", "Affluent", "Elite", "Poverty", "Struggling", "Comfortable"],
        "Politics": ["Anarchist", "Authoritarian", "Centrist", "Conservative", "Left-wing", "Liberal", "Libertarian", "Moderate", "Populist", "Progressive", "Right-wing"],
        "Race": ["African", "Asian", "Black", "East Asian", "Hispanic", "Indigenous", "Middle Eastern", "Mixed Race", "Pacific Islander", "South Asian", "White"],
        "Religion": ["Agnostic", "Atheist", "Baháʼí", "Buddhist", "Christian", "Hindu", "Jain", "Jewish", "Muslim", "Sikh", "Taoist"]
    }

    payload = {
        "image": img_b64,
        "categories": categories
    }

    url = "http://localhost:5000/sdapi/v1/interrogate/structured"
    print(f"Sending request to {url} with {len(categories)} categories...")
    
    try:
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print("\nResponse:")
            print(json.dumps(data, indent=2))
    except Exception as e:
        print(f"\nError: {e}")

if __name__ == "__main__":
    test_interrogate()
