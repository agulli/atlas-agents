import os
import yaml

def dynamically_load_skills(directory_path="shared/declarative_skills/"):
    """
    Parses YAML frontmatter from .md files to build the agent's tool registry automatically.
    This is the exact implementation discussed in Chapter 3 section 3.7.
    """
    skills = []
    for filename in os.listdir(directory_path):
        if not filename.endswith(".md"): continue
        
        with open(os.path.join(directory_path, filename), "r") as f:
            content = f.read()
            
        # Extract YAML frontmatter
        if content.startswith("---"):
            frontmatter_end = content.find("---", 3)
            if frontmatter_end == -1:
                continue  # Malformed frontmatter, skip
            yaml_str = content[3:frontmatter_end]
            meta = yaml.safe_load(yaml_str)
            body = content[frontmatter_end+3:].strip()
            
            skills.append({
                "name": filename.replace(".md", ""),
                "description": meta.get("description", "A loaded skill"),
                "system_prompt": body
            })
    return skills\n