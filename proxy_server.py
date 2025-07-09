import os
import json
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
        return jsonify({"error": "A search query parameter 'q' is required."}), 400

    # --- Construct JQL ---
    clauses = []
    if project_key:
        clauses.append(f'project = "{project_key.upper()}"')
    
    sanitized_search = user_query.replace('"', '\\"')
    # This updated clause searches both the ticket ID (issuekey) and the text fields.
    # It converts the search for issuekey to uppercase to match JIRA's format.
    search_clause = f'(issuekey ~ "{sanitized_search.upper()}" OR text ~ "{sanitized_search}*")'
    clauses.append(search_clause)
    
    jql_query = " AND ".join(clauses) + " ORDER BY updated DESC"

    # --- Call Jira API ---
    search_url = f"{JIRA_URL}/rest/api/3/search"
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Accept": "application/json"}
    query_data = {'jql': jql_query, 'fields': ["summary", "key"], 'maxResults': 25}

    try:
        response = requests.post(search_url, headers=headers, auth=auth, json=query_data, timeout=10)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        
        results = response.json()
        simplified_issues = [{'key': issue['key'], 'summary': issue['fields']['summary']} for issue in results.get('issues', [])]
        
        return jsonify(simplified_issues)

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Failed to connect to Jira: {str(e)}"}), 502
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

# This allows the app to be run by a production server like Gunicorn
if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 8080)))
