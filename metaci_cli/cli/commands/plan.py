# -*- coding: utf-8 -*-

"""Console script for metaci_cli."""

import click
from metaci_cli.cli.commands.main import main
from metaci_cli.cli.util import lookup_repo
from metaci_cli.cli.util import render_recursive
from metaci_cli.cli.config import pass_config
from metaci_cli.metaci_api import ApiClient

@click.group('plan')
def plan():
    pass

def prompt_org(api_client, config, repo_id):
    params = {'repo': repo_id}
    res = api_client('orgs', 'list', params=params)
    orgs = {}
    for org in res['results']:
        orgs[org['name']] = org['id']
    orgs = orgs.keys()
    orgs.sort()

    click.echo('Valid org choices: {}'.format(', '.join(orgs)))
    org = click.prompt('Org')
    if org not in orgs:
        raise click.UsageError('Org {} not found.  Check metaci org list.'.format(org))
    return org

@click.command(name='create', help='Create a new Plan to run builds on MetaCI')
@pass_config
def plan_create(config):
    if not config.project_config:
        raise click.UsageError('You must be inside a local git repository configured for CumulusCI.  No CumulusCI configuration was detected in the local directory')

    api_client = ApiClient(config)

    params = {}

    # Filter by repository
    repo_data = lookup_repo(api_client, config, None, required=True)
    params['repo'] = repo_data['id']

    click.echo('# Name and Description')
    click.echo('Provide a name and description of the build plan you are creating')
    name = click.prompt('Name')
    description = click.prompt('Description')

    click.echo()
    click.echo('# Org')    
    click.echo('Select the MetaCI org this plan should run its builds against.  If the org does not yet exist, use metaci org create to create the org first.')
    org = prompt_org(api_client, config, repo_data['id'])

    flows_list = config.project_config.flows.keys()
    flows_list.sort()
    click.echo()
    click.echo('# Flows')
    click.echo('What CumulusCI flows should this plan run?  You can enter multiple flows using a comma as a separator')
    click.echo('Available Flows: {}'.format(', '.join(flows_list)))
    flows = click.prompt('Flow(s)')

    click.echo()
    click.echo('# Trigger Type')
    click.echo('How should this plan be triggered?')
    click.echo('  - commit: Trigger on branch commits matching a regex pattern')
    click.echo('  - tag: Trigger on new tags matching a regex pattern')
    click.echo('  - manual: Do not auto-trigger any builds.  Can be manually triggered.')
    trigger_type = click.prompt('Trigger Type (commit, tag, or manual)')
    if trigger_type == 'commit':
        regex = click.prompt('Branch Match RegEx (ex feature/.*)')
    elif trigger_type == 'tag':
        regex = click.prompt('Tag Match RegEx (ex beta/.*)')
    elif trigger_type != 'manual':
        raise click.UsageError('{} is an invalid trigger type.  Valid choices are: commit, tag, manual')
    else:
        regex = None

    click.echo()
    click.echo('# Github Commit Status')
    click.echo('MetaCI can set the build status via the Github Commit Status API.  Commit statuses are grouped by a context field.  Setting a different context on different plans will cause multiple commit statuses to be created for each unique context in Github.')
    context = None
    if click.confirm('Set commit status in Github for this plan?', default=True):
        context = click.prompt('Github Commit Status Context', default=name)

    if trigger_type == 'manual':
        active = True
    else:
        click.echo()
        click.echo('# Activate Plan')
        match_str = 'matching regex {}'.format(regex) if regex else ''
        click.echo('If active, this plan will automatically build on new {}s{}'.format(trigger_type, match_str))
        active = click.confirm('Active?', default=True)
    
    click.echo()
    click.echo('# Public or Private')
    click.echo('Public plans and their builds are visible to anonymous users.  This is recommended for open source projects, instances on an internal network or VPN, or projects that want transparency of their build information.  Private plans are only visible to logged in users who have been granted the Is Staff role by an admin.')
    public = click.confirm('Public?')
        
    params = {
        'name': name,    
        'description': description,    
        'org': org,    
        'flows': flows,    
        'type': trigger_type,    
        'regex': regex,    
        'context': context,    
        'active': active,    
        'public': public,    
        'repo_id': repo_data['id'],    
    }

    res = api_client('plans', 'create', params=params)

    click.echo()
    click.echo('Created plan {} with the following configuration'.format(name))
    render_recursive(res)


@click.command(name='list', help='Lists plans')
@click.option('--repo', help="Specify the repo in format OwnerName/RepoName")
@pass_config
def plan_list(config, repo):
    api_client = ApiClient(config)

    params = {}

    # Filter by repository
    repo_data = lookup_repo(api_client, config, repo)
    if repo_data:
        params['repo'] = repo_data['id']

    res = api_client('plans', 'list', params=params)

    plan_list_fmt = '{id:<5} {name:24.24} {org:12.12} {flows:24.24} {type:7.7} {regex}'
    headers = {
        'id': '#',
        'name': 'Status',
        'org': 'Org',
        'flows': 'Flows',
        'type': 'Trigger',
        'regex': 'Regex',
    }
    click.echo(plan_list_fmt.format(**headers))
    for plan in res['results']:
        click.echo(plan_list_fmt.format(**plan))

plan.add_command(plan_create)
plan.add_command(plan_list)
main.add_command(plan)
