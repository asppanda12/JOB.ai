# Visualize the pipeline using networkx and matplotlib
import networkx as nx
import matplotlib.pyplot as plt

Linkedin="Linkedin/"
naukri="Naukri/"
instahyre="Scrape_entire_web/"
data_cleaning="data_cleaning/"
cuvete="Cuvete/"

pipeline = {
    f"{Linkedin}start_scrapping_v2_step_1.py": f"{Linkedin}drop_duplicates_linked_step_2.py",
    f"{Linkedin}drop_duplicates_linked_step_2.py": f"{Linkedin}clean_output_step3.py",
    f"{Linkedin}clean_output_step3.py": f"{Linkedin}create_json_linkedin_step4.py",
    f"{Linkedin}create_json_linkedin_step4.py": f"{data_cleaning}clean_data_linkedin.py",

    f"{naukri}start_scrapping.py": f"{naukri}create_json_naukri.py",
    f"{naukri}create_json_naukri.py": f"{data_cleaning}clean_data_naukri.py",

    f"{instahyre}instahyre_for_1yoe.py": f"{instahyre}instahyre_for_fresher.py",
    f"{instahyre}instahyre_for_fresher.py": f"{instahyre}instahyre.py",
    f"{instahyre}instahyre.py": f"{data_cleaning}clean_data_instahyre.py",

    f"{cuvete}start_scrapping.py": f"{cuvete}create_json_cuvete.py",
    f"{cuvete}create_json_cuvete.py": f"{data_cleaning}clean_data_cuvete.py",
}

# Split pipelines into 4 groups
groups = {
    "LinkedIn": {k:v for k,v in pipeline.items() if k.startswith(Linkedin)},
    "Naukri": {k:v for k,v in pipeline.items() if k.startswith(naukri)},
    "Instahyre": {k:v for k,v in pipeline.items() if k.startswith(instahyre)},
    "Cuvete": {k:v for k,v in pipeline.items() if k.startswith(cuvete)},
}

# Plot each group separately
fig, axes = plt.subplots(2, 2, figsize=(16, 12))
axes = axes.flatten()

for i, (name, sub_pipeline) in enumerate(groups.items()):
    G = nx.DiGraph()
    for parent, child in sub_pipeline.items():
        G.add_edge(parent, child)
    
    pos = nx.spring_layout(G, seed=42)
    nx.draw(G, pos, with_labels=True, node_color="lightgreen", node_size=3000, 
            edge_color="black", font_size=9, arrows=True, ax=axes[i])
    axes[i].set_title(f"{name} Pipeline", fontsize=14)

plt.suptitle("Parallel Pipelines", fontsize=16)
plt.show()
