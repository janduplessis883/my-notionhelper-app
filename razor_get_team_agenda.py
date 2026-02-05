from notionhelper import NotionHelper
import json

# Authentication
# TIP: Move this to an environment variable later for better security!

nh = NotionHelper(NOTION_TOKEN)

def get_team_agenda():
    # Fetch the data
    work = nh.get_data_source_pages_as_dataframe()
    current = work[work['Discussed'] == False]
    # Select columns and rename them to match your lowercase/snake_case requirements
    df_subset = current[['Discussed', 'Agenda Item', 'Brief Description', 'Person']].copy()
    df_subset.columns = ['discussed', 'agenda_item', 'brief_description', 'person']
    df_subset.sort_values(by='agenda_item', ascending=True, inplace=True, ignore_index=True)

    # Convert the DataFrame to a list of dictionaries
    result = df_subset.to_dict(orient='records')
    return result

if __name__ == '__main__':
    agenda = get_team_agenda()

    # Using json.dumps to print it with nice formatting (indentation)
    print(json.dumps(agenda, indent=2))
