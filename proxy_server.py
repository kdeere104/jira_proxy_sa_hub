import os
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
    This uses the JIRA Issue Picker API, which is designed for fast,
    interactive searches and supports partial matching on issue keys.
    """
    user_query = request.args.get("q")
    project_key = request.args.get("project")

    # --- Validation ---
    if not all([JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN]):
        return jsonify({"error": "Backend server is missing JIRA configuration."}), 500

    if not user_query or not user_query.strip():
        return jsonify([])

    # --- Call Jira Issue Picker API ---
    # This endpoint is specifically designed for UI pickers and supports partial matching.
    picker_url = f"{JIRA_URL}/rest/api/3/issue/picker"
    auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Accept": "application/json"}
    
    params = {'query': user_query.strip()}
    
    # If a project key is provided, scope the search to that project.
    if project_key and project_key.strip():
        # Using currentJQL to filter by project
        params['currentJQL'] = f'project = "{project_key.strip().upper()}"'

    try:
        response = requests.get(picker_url, headers=headers, auth=auth, params=params, timeout=10)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        
        picker_results = response.json()
        
        # --- Process and Format Results ---
        # The picker API returns sections of issues. We need to parse them,
        # combine them, and remove duplicates.
        found_issues = {} # Use a dict to handle duplicates automatically based on key
        
        for section in picker_results.get('sections', []):
            for issue in section.get('issues', []):
                issue_key = issue.get('key')
                if issue_key:
                    # Use summaryText as it's the plain text version, fallback to summary
                    summary = issue.get('summaryText', issue.get('summary', 'No summary available'))
                    found_issues[issue_key] = {'key': issue_key, 'summary': summary}
        
        # Convert the dict of unique issues back to a list that the frontend expects
        simplified_issues = list(found_issues.values())
        
        return jsonify(simplified_issues)

    except requests.exceptions.HTTPError as e:
        error_details = f"Jira returned HTTP {e.response.status_code}: {e.response.reason}"
        try:
            # Try to get a more specific error message from Jira's response
            jira_error = e.response.json()
            if 'errorMessages' in jira_error and jira_error['errorMessages']:
                 error_details = f"Jira Error: {', '.join(jira_error['errorMessages'])}"
        except ValueError: # Catches JSONDecodeError if body isn't valid JSON
            pass
        
        print(f"JIRA API Error: {error_details}")
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
