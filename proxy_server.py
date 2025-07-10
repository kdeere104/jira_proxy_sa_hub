import os
import json
import re
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from requests.auth import HTTPBasicAuth

# Initialize Flask App & CORS
app = Flask(__name__)
CORS(app) 

# Get credentials from environment variables
JIRA_URL = os.environ.get("JIRA_URL")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN")

@app.route("/search-jira", methods=["GET"])
def jira_search_endpoint():
    """
    An API endpoint that the frontend will call.
    It expects a query parameter like: /search-jira?q=some-term
    """
    user_query = request.args.get("q")
    project_key = request.args.get("project")

    if not all([JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN]):
        return jsonify({"error": "Backend server is missing JIRA configuration."}), 500

    if not user_query:
        return jsonify([])

    # --- Robust JQL Construction ---
    sanitized_search = user_query.replace('"', '\\"')
    cleaned_search = sanitized_search.rstrip('*? ')

    if not cleaned_search:
        return jsonify([])

    # Define clauses for the main JQL query
    clauses = []
    if project_key:
        clauses.append(f'project = "{project_key.upper()}"')
    
    # --- THE FIX ---
    # Regex to check if the search term looks like a complete JIRA issue key (e.g., PROJ-123).
    # This prevents sending syntactically invalid JQL like `issuekey = "SCR"`.
    issue_key_complete_pattern = re.compile(r'^[a-z0-9_]+-\d+$', re.IGNORECASE)

    # Always search in the general text fields.
    search_clause_components = [f'text ~ "{cleaned_search}*"']
    
    # ONLY if the search term looks like a complete key, add an OR condition
    # to search the 'issuekey' field directly. This is more precise and avoids errors.
    if issue_key_complete_pattern.fullmatch(cleaned_search):
        search_clause_components.append(f'issuekey = "{cleaned_search.upper()}"')
    
    # Combine the search conditions with OR.
    # This will be either `(text ~ "...")` or `((text ~ "...") OR issuekey = "...")`
    search_clause = f'({" OR ".join(search_clause_components)})'
    clauses.append(search_clause)
    
    jql_query = " AND ".join(clauses) + " ORDER BY updated DESC"

    # --- Call Jira API ---
    search_url = f"{JIRA_URL}/rest/api/3/search"
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Accept": "application/json"}
    query_data = {'jql': jql_query, 'fields': ["summary", "key"], 'maxResults': 25}

    try:
        response = requests.post(search_url, headers=headers, auth=auth, json=query_data, timeout=10)
        response.raise_for_status() 
        
        results = response.json()
        simplified_issues = [{'key': issue['key'], 'summary': issue['fields']['summary']} for issue in results.get('issues', [])]
        
        return jsonify(simplified_issues)

    except requests.exceptions.HTTPError as e:
        error_details = f"Jira returned HTTP {e.response.status_code}: {e.response.reason}"
        try:
            jira_error = e.response.json()
            if 'errorMessages' in jira_error and jira_error['errorMessages']:
                 error_details = f"Jira Error: {', '.join(jira_error['errorMessages'])}"
            elif 'errors' in jira_error and jira_error['errors']:
                 error_details = f"Jira Field Error: {json.dumps(jira_error['errors'])}"
        except json.JSONDecodeError:
            pass
        
        print(f"JIRA API Error: {error_details}")
        return jsonify({"error": error_details}), e.response.status_code

    except requests.exceptions.RequestException as e:
        print(f"Connection Error: {str(e)}")
        return jsonify({"error": f"Failed to connect to Jira: {str(e)}"}), 502
    except Exception as e:
        print(f"Unexpected Error: {str(e)}")
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 8080)))
