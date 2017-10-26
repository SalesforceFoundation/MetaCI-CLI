# -*- coding: utf-8 -*-

"""Console script for metaci_cli."""

import click
import heroku3
import json
import os
import requests
import subprocess
import time
import webbrowser
from cumulusci.core.config import ServiceConfig
from cumulusci.core.exceptions import ServiceNotConfigured
from metaci_cli.cli.commands.main import main
from metaci_cli.cli.util import render_recursive
from metaci_cli.cli.config import pass_config

@click.group('site')
def site():
    pass

def verify_overwrite(config):
    try:
        service = config.keychain.get_service('metaci')
    except ServiceNotConfigured:
        return

    click.echo('Site {} is currently configured.  Connecting to a new site will delete the local configuration for the current site.  You can always use metaci site connect to reconnect to an existing site.'.format(service.url))
    click.confirm(
        click.style(
            'Are you sure you want to connect to a new site?',
            bold=True,
            fg='red',
        ),
        abort=True
    )
    return service

def check_current_site(config):
    try:
        service = config.keychain.get_service('metaci')
    except ServiceNotConfigured:
        raise click.UsageError('No site is currently connected.  Use metaci site connect or metaci site create to connect to a site')
    return service

@click.command(name='browser', help='Opens the MetaCI site in a browser tab')
@pass_config
def site_browser(config):
    service = check_current_site(config)
    click.echo('Opening browser to {}'.format(service.url))
    webbrowser.open(service.url)

app_shape_choice = click.Choice(['dev','staging','prod'])

@click.command(name='create', help='Deploy a new Heroku app running MetaCI')
@click.option('--name', help='Specify an app name instead of prompting for it')
@click.option('--shape', 
    help='Specify an app shape instead of prompting for it', 
    type=app_shape_choice,
)
@pass_config
def site_create(config, name, shape):
    if not config.project_config:
        raise click.ClickException('You must be in a CumulusCI configured local git repository.')
   
    verify_overwrite(config)

    # Initialize payload
    payload = {
        'app': {},
        'source_blob': {
            'url': 'https://github.com/SalesforceFoundation/mrbelvedereci/tarball/feature/api/',
       },
    }
    env = {} 

    # Heroku API Token
    try:
        token = subprocess.check_output(['heroku','auth:token']).strip()
    except:
        click.echo()
        click.echo(click.style('# Heroku API Token', bold=True, fg='blue'))
        click.echo('Enter your Heroku API Token.  If you do not have a token, go to the Account page in Heroku and use the API Token section: https://dashboard.heroku.com/account')
        click.echo(click.style(
            'NOTE: For security purposes, your input will be hidden.  Paste your API Token and hit Enter to continue.',
            fg='yellow',
        ))
        token = click.prompt('API Token', hide_input=True)

    heroku_api = heroku3.from_key(token)

    # App Name
    if not name:
        click.echo()
        click.echo(click.style('# Heroku App Name', bold=True, fg='blue'))
        click.echo('Specify the name of the Heroku app you want to create.')
        payload['app']['name'] = click.prompt('App Name')
    else:
        payload['app']['name'] = name

    # App Shape
    if not shape:
        click.echo()
        click.echo(click.style('# Heroku App Shape', bold=True, fg='blue'))
        click.echo('Select the Heroku app shape you want to deploy.  Available options:')
        click.echo('  - dev: Runs on free Heroku resources with build concurrency of 1')
        click.echo('  - staging: Runs on paid Heroku resources with fixed build concurrency of X')
        click.echo('  - prod: Runs on paid Heroku resources auto-scaled build concurrency via Hirefire.io (paid add on configured separately)')
        app_shape = click.prompt('App Shape', type=app_shape_choice, default='dev')

    # Hirefire Token
    if app_shape == 'prod':
        click.echo()
        click.echo(click.style('# Hirefire Token', bold=True, fg='blue'))
        click.echo('The prod app shape requires the use of Hirefire.io to scale the build worker dynos.  You will need to have an account on Hirefire.io and get the API token from your account.')
        env['HIREFIRE_TOKEN'] = click.prompt('Hirefire API Token')

    # Salesforce DX
    click.echo()
    click.echo(click.style('# Salesforce DX Configuration', bold=True, fg='blue'))
    click.echo('The following prompts collect information from your local Salesforce DX configuration to use to configure MetaCI to use sfdx')

    # Salesforce DX Hub Key
    click.echo()
    click.echo('MetaCI uses JWT to connect to your Salesforce DX devhub.  Please enter the path to your local private key file.  If you have not set up JWT for your devhub, refer to the documentation: https://developer.salesforce.com/docs/atlas.en-us.sfdx_dev.meta/sfdx_dev/sfdx_dev_auth_jwt_flow.htm')
    sfdx_private_key = click.prompt(
        'Path to private key',
        type=click.Path(readable=True, dir_okay=False),
        default=os.path.expanduser('~/.ssh/sfdx_server.key'),
    )
    with open(sfdx_private_key, 'r') as f:
        env['SFDX_HUB_KEY'] = f.read()

    # Salesforce DX Client ID
    click.echo()
    click.echo('Enter the Connected App Client ID you used for the JWT authentication flow to the Salesforce DX devhub.')
    click.echo(click.style(
        'NOTE: For security purposes, your input will be hidden.  Paste your Client ID and hit Enter to continue.',
        fg='yellow',
    ))
    env['SFDX_CLIENT_ID'] = click.prompt('Client ID', hide_input=True)

    # Salesforce DX Username
    try:
        devhub = subprocess.check_output(['sfdx','force:config:get', 'defaultdevhubusername', '--json']).strip()
        devhub = json.loads(devhub)
        devhub = devhub['result'][0]['value']
    except:
        devhub = None
   
    if devhub:
        env['SFDX_HUB_USERNAME'] = devhub
    else: 
        click.echo()
        click.echo('Enter the username MetaCI should use for JWT authentication to the Salesforce DX devhub.')
        env['SFDX_HUB_USERNAME'] = click.prompt('Username')

    # Get connected app info from CumulusCI keychain
    connected_app = config.keychain.get_connected_app()
    env['CONNECTED_APP_CALLBACK_URL'] = connected_app.callback_url
    env['CONNECTED_APP_CLIENT_ID'] = connected_app.client_id
    env['CONNECTED_APP_CLIENT_SECRET'] = connected_app.client_secret

    # Set the site url
    env['SITE_URL'] = 'https://{}.herokuapp.com'.format(payload['app']['name'])

    # Get Github credentials from CumulusCI keychain
    github = config.keychain.get_service('github')
    env['GITHUB_USERNAME'] = github.username
    env['GITHUB_PASSWORD'] = github.password
    env['GITHUB_WEBHOOK_BASE_URL'] = '{SITE_URL}/webhook/github'.format(**env)
    env['FROM_EMAIL'] = github.email

    # Prepare the payload 
    payload['overrides'] = {
        'env': env,
    } 

    # Create the new Heroku App
    headers = {
        'Accept': 'application/vnd.heroku+json; version=3',
        'Authorization': 'Bearer {}'.format(token),
    }
    resp = requests.post('https://api.heroku.com/app-setups', json=payload, headers=headers)
    if resp.status_code != 202:
        raise click.ClickException('Failed to create Heroku App.  Reponse code [{}]: {}'.format(resp.status_code, resp.json()))
    app_setup = resp.json()
    
    # Check status
    status = app_setup['status']
    click.echo()
    click.echo('Status: {}'.format(status))
    click.echo(click.style('Creating app:', fg='yellow'))
    i = 1
    build_started = False
    with click.progressbar(length=200) as bar:
        while status in ['pending']:
            check_resp = requests.get(
                'https://api.heroku.com/app-setups/{id}'.format(**app_setup),
                headers=headers,
            )
            if check_resp.status_code != 200:
                raise click.ClickException('Failed to check status of app creation.  Reponse code [{}]: {}'.format(check_resp.status_code, check_resp.json()))
            check_data = check_resp.json()

            # Stream the build log output once the build starts
            if not build_started and check_data['build'] != None:
                build_started = True
                click.echo()
                click.echo()
                click.echo(click.style('Build {id} Started:'.format(**check_data['build']), fg='yellow'))
                build_stream = requests.get(check_data['build']['output_stream_url'], stream=True, headers=headers)
                for chunk in build_stream.iter_content():
                    click.echo(chunk, nl=False)

            # If app-setup is still pending, sleep and then poll again
            if check_data['status'] != 'pending':
                bar.update(100)
                break
            if i < 98:
                i += 1
                bar.update(i)
            time.sleep(2)

    click.echo()
    # Success
    if check_data['status'] == 'succeeded':
        click.echo(click.style('Heroku app creation succeeded!', fg='green', bold=True))
        render_recursive(check_data)
    # Failed
    elif check_data['status'] == 'failed':
        click.echo(click.style('Heroku app creation failed', fg='red', bold=True))
        render_recursive(check_data)
        click.echo()
        click.echo('Build Info:')
        resp = requests.get('https://api.heroku.com/builds/{id}'.format(**check_data['build']), headers=headers)
        render_recursive(resp.json())
        return
    else:
        raise click.ClickException('Received an unknown status from the Heroku app-setups API.  Full API response: {}'.format(check_data))

    # Apply the app shape
    if app_shape == 'staging':
        pass
    elif app_shape == 'prod':
        pass

    click.echo()
    click.echo(click.style('# Create Admin User', bold=True, fg='blue'))
    click.echo('You will need an initial admin user to start configuring your new MetaCI site.  Enter a password for the admin user and one will be created for you')
    password = click.prompt('Password', hide_input=True, confirmation_prompt=True)
    

    # Create the admin user
    click.echo()
    click.echo(click.style('Creating admin user:', fg='yellow'))
    command = 'python manage.py autoadminuser {FROM_EMAIL}'.format(**env)
    heroku_app = app = heroku_api.app(check_data['app']['id'])
    admin_output, dyno = app.run_command(command, printout=True, env={'ADMINUSER_PASS': password})
    click.echo(admin_output.splitlines()[-1:])
    
    # Create the admin user's API token
    click.echo()
    click.echo(click.style('Generating API token for admin user:', fg='yellow'))
    command = 'python manage.py usertoken admin'
    token_output, dyno = app.run_command(command)
    for line in token_output.splitlines():
        if line.startswith('Token: '):
            api_token = line.replace('Token: ', '', 1).strip()

    if api_token:
        service = ServiceConfig({
            'url': env['SITE_URL'],
            'token': api_token,
        })
        config.keychain.set_service('metaci', service)
        click.echo(click.style('Successfully connected metaci to the new site at {SITE_URL}'.format(**env), fg='green', bold=True))
    else:
        click.echo(click.style('Failed to create API connection to new metaci site at {SITE_URL}.  Try metaci site connect'.format(**env), fg='red', bold=True))

    

@click.command(name='connect', help='Connects to an existing MetaCI instance')
@pass_config
def site_connect(config):
    verify_overwrite(config)
    url = click.prompt('Site Base URL')
    click.echo('Contact your MetaCI administrator to get an API Token.  Tokens can be created by administrators in the admin panel under Auth Tokens -> Tokensi.')
    click.echo(click.style(
        'NOTE: For security purposes, your input will be hidden.  Paste your API Token and hit Enter to continue.',
        fg='yellow',
    ))
    token = click.prompt('API Token', hide_input=True)
    service = ServiceConfig({
        'url': url,
        'token': token,
    })
    config.keychain.set_service('metaci', service)

@click.command(name='info', help='Displays info about the current MetaCI site')
@pass_config
def site_info(config):
    service = check_current_site(config)
    render_recursive(service.config)


site.add_command(site_browser)
site.add_command(site_create)
site.add_command(site_connect)
site.add_command(site_info)
main.add_command(site)