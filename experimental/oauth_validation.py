import requests
from requests.auth import HTTPBasicAuth

def validate_token(token, introspection_url, client_id, client_secret):
    """
    Validate an OAuth access token using PingFederate's introspection endpoint.

    :param token: The OAuth access token to be validated.
    :param introspection_url: The URL of PingFederate's token introspection endpoint.
    :param client_id: The client ID for basic authentication.
    :param client_secret: The client secret for basic authentication.
    :return: A dictionary containing the token information if valid, raises an exception if invalid.
    """
    try:
        response = requests.post(
            introspection_url,
            data={'token': token},
            auth=HTTPBasicAuth(client_id, client_secret),
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        
        # Check if the request was successful
        if response.status_code == 200:
            token_info = response.json()
            
            # Check if the token is active
            if token_info.get('active'):
                return token_info
            else:
                raise ValueError("Token is not active")
        else:
            response.raise_for_status()
    
    except requests.exceptions.RequestException as e:
        raise Exception(f"An error occurred while validating the token: {e}")

# Example usage
if __name__ == "__main__":
    token = "<bearer-token>"
    introspection_url = "https://<pingfederate-server>/as/introspect.oauth2"
    client_id = "<your-client-id>"
    client_secret = "<your-client-secret>"

    try:
        token_info = validate_token(token, introspection_url, client_id, client_secret)
        print("Token is valid:", token_info)
    except ValueError as e:
        print(e)
    except Exception as e:
        print("An error occurred:", e)