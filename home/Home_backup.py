import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
import streamlit.components.v1 as components
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import plotly.express as px
from copyright import display_custom_license
import numpy as np
import plotly.express as px
import time
from sidebar_content import sidebar_content
import concurrent.futures

st.set_page_config(layout = "wide", 
                    page_title='OpenAlex DOI Search Tool',
                    page_icon="https://openalex.org/img/openalex-logo-icon-black-and-white.ea51cede.png",
                    initial_sidebar_state="auto") 
pd.set_option('display.max_colwidth', None)

sidebar_content() 

st.title('OpenAlex DOI Search Tool', anchor=False)

df_dois = None

radio = st.radio('Select an option', ['Insert DOIs', 'Upload a file with DOIs'])
if radio == 'Insert DOIs':
    st.write('Please insert [DOIs](https://www.doi.org/) (commencing "10.") in separarate rows.')
    dois = st.text_area(
        'Type or paste in one DOI per line in this box, then press Ctrl+Enter.', 
        help='DOIs will be without a hyperlink such as 10.1136/bmjgh-2023-013696',
        placeholder=''' e.g.
        10.1136/bmjgh-2023-013696
        10.1097/jac.0b013e31822cbdfd
        '''
        )
    # Split the input text into individual DOIs based on newline character
    doi_list = dois.split('\n')
    
    # Remove any empty strings that may result from extra newlines
    doi_list = [doi.strip() for doi in doi_list if doi.strip()]
    
    # Create a DataFrame
    df_dois = pd.DataFrame(doi_list, columns=["doi_submitted"])
else:
    st.write('Please upload and submit a .csv file of [DOIs](https://www.doi.org/) (commencing “10.") in separate rows.')
    st.warning('The title of the column containing DOIs should be one of the followings: doi, DOI, dois, DOIs, Hyperlinked DOI. Otherwise the tool will not identify DOIs.')
    dois = st.file_uploader("Choose a CSV file", type="csv")

    if dois is not None:
        try:
            df = pd.read_csv(dois, engine='python')  # more tolerant to inconsistent rows
        except pd.errors.ParserError as e:
            st.error("There was a problem parsing your CSV file. Check for stray commas or improperly quoted values.")
            st.exception(e)
            st.stop()
        
        doi_columns = ['doi', 'DOI', 'dois', 'DOIs', 'Hyperlinked DOI']
        doi_column = next((col for col in doi_columns if col in df.columns), None)
        
        if doi_column:
            df_dois = df[[doi_column]]
            df_dois.columns = ['doi_submitted']
        else:
            st.error('''
            No DOI column in the file.
            
            Make sure that the column listing DOIs have one of the following names:
            'doi', 'DOI', 'dois', 'DOIs', 'Hyperlinked DOI'
            ''')
            st.stop()
    else:
        st.write("Please upload a CSV file containing DOIs.")

# if df_dois is not None:
#     st.error('Please enter 500 or fewer DOIs')
# else:
if dois:
    df_dois = df_dois.dropna()
    df_dois['doi_submitted'] = df_dois['doi_submitted'].str.replace('https://doi.org/', '')
    df_dois = df_dois.drop_duplicates().reset_index(drop=True)
    no_dois = len(df_dois)
    if len(df_dois) > 100:
        st.toast('You entered over 100 DOIs. It may take some time to retrieve results. Please wait.')
    if len(df_dois) >100:
        st.warning('You entered over 100 DOIs. It may take some time to retrieve results.')
    st.info(f'You entered {no_dois} unique DOIs')
    with st.expander(f'See the DOIs you entered'):
        df_dois

    submit = st.button('Search DOIs', icon=":material/search:")
    
    if submit or st.session_state.get('status_expanded', False):
        if submit:
            st.session_state['status_expanded'] = True
        with st.status("Searching DOIs in OpenAlex", expanded=st.session_state.get('status_expanded', True)) as status:
            df_dois['doi_submitted'] = df_dois['doi_submitted'].str.replace('https://doi.org/', '', regex=False)

            # df = pd.read_csv('your_doi_file.csv') or use your existing df
            df_dois['doi_submitted'] = df_dois['doi_submitted'].str.strip().str.replace('https://doi.org/', '', regex=False)

            # Function to batch DOIs
            def batch_dois(dois, batch_size=20):
                for i in range(0, len(dois), batch_size):
                    yield dois[i:i + batch_size]

            # Store results
            all_results = []

            # Process in batches
            def fetch_batch(batch):
                filter_string = '|'.join(batch)
                url = f"https://api.openalex.org/works?filter=doi:{filter_string}&mailto="
                response = requests.get(url)
                if response.status_code == 200:
                    return response.json().get('results', [])
                else:
                    return []

            # Run batches in parallel
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = [executor.submit(fetch_batch, batch) for batch in batch_dois(df_dois['doi_submitted'].tolist(), 20)]
                for future in concurrent.futures.as_completed(futures):
                    all_results.extend(future.result())

            # Normalize and flatten nested fields
            results_df = pd.json_normalize(all_results, sep='.')

            # Add cleaned DOI for merging
            if not results_df.empty and 'doi' in results_df.columns:
                results_df['doi_submitted'] = results_df['doi'].str.replace('https://doi.org/', '', regex=False)

                # Merge with original DOIs
                merged_df = df_dois.merge(results_df, on='doi_submitted', how='left')
                
                if merged_df['id'].isnull().all():
                    st.warning("No DOIs found in the OpenAlex database.")
                else:
                    num_results = merged_df['id'].notnull().sum()
                    st.success(f"{num_results} result(s) found.")

                oa_status_summary = merged_df['open_access.oa_status'].value_counts(dropna=False).reset_index()
                oa_status_summary.columns = ['OA status', '# Outputs']
                merged_df['open_access.is_oa'] = merged_df['open_access.is_oa'].map({True: 'Open Access', False: 'Closed Access'})
                oa_summary = merged_df['open_access.is_oa'].value_counts(dropna=False).reset_index()
                oa_summary.columns = ['Is OA?', '# Outputs']
                st.subheader("Open Access Status Summary", anchor=False)
                if len(oa_summary) >= 2:
                    items = [
                        f"**{row['# Outputs']}** *{row['Is OA?']}*"
                        for _, row in oa_summary.iterrows()
                    ]
                    st.write(f"{' and '.join(items)} papers found")
                elif len(oa_summary) == 1:
                    st.write(f'''
                        **{oa_summary.iloc[0]['# Outputs']}** *{oa_summary.iloc[0]['Is OA?']}* papers found.
                    ''')
                st.dataframe(oa_status_summary, hide_index =True,  use_container_width=False)

                # JOURNALS
                top_journals = merged_df['primary_location.source.display_name'].value_counts(dropna=False).reset_index()
                top_journals.columns = ['Journal name', '# Outputs']
                top_journals = top_journals.dropna()
                st.subheader("Journals", anchor=False)
                st.dataframe(top_journals, hide_index=True,  use_container_width=False)

                # AUTHORS
                authors_df = merged_df.explode('authorships').reset_index(drop=True)
                authors_df = pd.json_normalize(authors_df['authorships']).reset_index(drop=True)
                authors_table = authors_df[[
                    'author.display_name',
                    'author.orcid',
                    'author_position',
                    'is_corresponding',
                    'raw_author_name'
                ]].drop_duplicates().reset_index(drop=True)

                # st.subheader("Authors", anchor=False)
                # st.dataframe(authors_table,  use_container_width=False)

                institutions_df = authors_df.explode('institutions').reset_index(drop=True)
                institution_details = pd.json_normalize(institutions_df['institutions']).reset_index(drop=True)
                institutions_df = pd.concat([
                    institutions_df.drop(columns=['institutions']).reset_index(drop=True),
                    institution_details
                ], axis=1)

                institutions_table = institutions_df[[
                    'author.display_name',
                    'display_name',      # Institution name
                    'country_code',
                    'type'
                ]].drop_duplicates().reset_index(drop=True)

                institutions_table.columns = ['author', 'institution', 'country_code', 'type']

                # st.subheader("Author Institutions")
                # st.dataframe(institutions_table,  use_container_width=False)

                # Institution frequency table
                institution_freq = institutions_table['institution'].value_counts(dropna=True).reset_index()
                institution_freq.columns = ['Institution', '# Count']
                st.subheader("Institutional Affiliations")
                st.dataframe(institution_freq, hide_index=True,  use_container_width=False)

                # Country frequency table
                country_freq = institutions_table['country_code'].value_counts(dropna=True).reset_index()
                country_freq.columns = ['Country Code', '# Count']
                st.subheader("Country Affiliations")
                st.dataframe(country_freq, hide_index=True,  use_container_width=False)

                status.update(label=f"Search complete! Results found for {num_results} DOIs", state="complete", expanded=True)

            else:
                st.error("No DOIs found in the OpenAlex database. Check the submitted DOIs and resubmit.")
                df_dois
                status.update(label=f"Search complete without any results!", state="complete", expanded=True)
else:
    st.warning("Enter DOIs in the text area or upload a file to calculate the Citation Source Index.")