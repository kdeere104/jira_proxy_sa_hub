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
        # Gracefully handle empty searches without sending a bad request to Jira.
        return jsonify([])

    # --- Robust JQL Construction ---
    # 1. Sanitize for JQL special characters (quotes).
    sanitized_search = user_query.replace('"', '\\"')
    # 2. Remove any user-added wildcards or trailing spaces to prevent syntax errors.
    #    The backend will add its own controlled wildcard.
    cleaned_search = sanitized_search.rstrip('*? ')

    # If after cleaning, the search is empty, return no results.
    if not cleaned_search:
        return jsonify([])

    clauses = []
    if project_key:
        clauses.append(f'project = "{project_key.upper()}"')
    
    # 3. Build a comprehensive search clause.
    #    - `issuekey ~ ...`: Searches for the ticket ID itself (e.g., "SCRUM-123").
    #    - `text ~ "...*"`: Performs a wildcard text search on summary, description, etc.
    search_clause = f'(issuekey ~ "{cleaned_search.upper()}" OR text ~ "{cleaned_search}*")'
    clauses.append(search_clause)
    
    jql_query = " AND ".join(clauses) + " ORDER BY updated DESC"

    # --- Call Jira API ---
    search_url = f"{JIRA_URL}/rest/api/3/search"
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Accept": "application/json"}
    query_data = {'jql': jql_query, 'fields': ["summary", "key"], 'maxResults': 25}

    try:
        response = requests.post(search_url, headers=headers, auth=auth, json=query_data, timeout=10)
        
        # This will automatically raise an exception for 4xx/5xx responses.
        response.raise_for_status() 
        
        results = response.json()
        simplified_issues = [{'key': issue['key'], 'summary': issue['fields']['summary']} for issue in results.get('issues', [])]
        
        return jsonify(simplified_issues)

    except requests.exceptions.HTTPError as e:
        # Provide a much more informative error message to the frontend.
        error_details = f"Jira returned HTTP {e.response.status_code}: {e.response.reason}"
        try:
            # Attempt to parse Jira's specific error message from the response body.
            jira_error = e.response.json()
            if 'errorMessages' in jira_error and jira_error['errorMessages']:
                 error_details = f"Jira Error: {', '.join(jira_error['errorMessages'])}"
            elif 'errors' in jira_error and jira_error['errors']:
                 error_details = f"Jira Field Error: {json.dumps(jira_error['errors'])}"
        except json.JSONDecodeError:
            # No JSON body, use the default HTTP error.
            pass
        
        print(f"JIRA API Error: {error_details}") # Log the detailed error on the server
        return jsonify({"error": error_details}), e.response.status_code

    except requests.exceptions.RequestException as e:
        print(f"Connection Error: {str(e)}")
        return jsonify({"error": f"Failed to connect to Jira: {str(e)}"}), 502
    except Exception as e:
        print(f"Unexpected Error: {str(e)}")
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500

# This allows the app to be run by a production server like Gunicorn
if __name__ == "__main__":
    app.run(port=int(os.environ.get("PORT", 8080)))
