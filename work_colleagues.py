from notionhelper import NotionHelper
import json

# Authentication
# TIP: Move this to an environment variable later for better security!

nh = NotionHelper(NOTION_TOKEN)

def get_work_colleagues():
    # Fetch the data
    work = nh.get_data_source_pages_as_dataframe(')

    # Select columns and rename them to match your lowercase/snake_case requirements
    df_subset = work[['Name', 'Job Title', 'Email']].copy()
    df_subset.columns = ['name', 'job_title', 'email']

    # Convert the DataFrame to a list of dictionaries
    result = df_subset.to_dict(orient='records')
    return result

if __name__ == '__main__':
    colleagues = get_work_colleagues()

    # Using json.dumps to print it with nice formatting (indentation)
    print(json.dumps(colleagues, indent=2))
