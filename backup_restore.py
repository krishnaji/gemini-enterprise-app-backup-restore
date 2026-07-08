#!/usr/bin/env python3
# /// script
# dependencies = [
#   "google-auth>=2.20.0",
#   "requests>=2.31.0",
# ]
# ///

import argparse
import json
import os
import sys
import time
import google.auth
import google.oauth2.service_account
from google.auth.transport.requests import AuthorizedSession

# Terminal coloring/style helpers
class Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"

def log_info(msg):
    print(f"{Style.BLUE}ℹ{Style.RESET} {msg}")

def log_success(msg):
    print(f"{Style.GREEN}✔{Style.RESET} {msg}")

def log_warning(msg):
    print(f"{Style.YELLOW}⚠{Style.RESET} {msg}")

def log_error(msg):
    print(f"{Style.RED}✘{Style.RESET} {msg}", file=sys.stderr)

def log_banner(title):
    border = "=" * 60
    print(f"\n{Style.CYAN}{border}")
    print(f"{Style.BOLD}{title.center(60)}")
    print(f"{Style.CYAN}{border}{Style.RESET}\n")

def get_credentials(scopes=None):
    """Gets Google Cloud credentials, prioritizing credentials.json if it exists."""
    if os.path.exists("credentials.json"):
        try:
            return google.oauth2.service_account.Credentials.from_service_account_file(
                "credentials.json",
                scopes=scopes
            )
        except Exception as e:
            log_warning(f"Failed to load credentials.json: {e}. Falling back to default credentials.")
            
    credentials, _ = google.auth.default(scopes=scopes)
    return credentials

def get_rest_endpoint(location):
    """Returns the correct REST endpoint base URL for the given location."""
    if location == "global":
        return "https://discoveryengine.googleapis.com"
    return f"https://{location}-discoveryengine.googleapis.com"

def get_default_project():
    """Attempts to resolve the default Google Cloud project ID."""
    if os.path.exists("credentials.json"):
        try:
            with open("credentials.json", "r") as f:
                data = json.load(f)
                return data.get("project_id")
        except Exception:
            pass
    try:
        _, project = google.auth.default()
        return project
    except Exception:
        return None

def get_session():
    """Returns an authorized Google API requests session."""
    creds = get_credentials(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return AuthorizedSession(creds)

def wait_for_operation(session, endpoint, operation_name, headers, timeout_seconds=300):
    """Polls a REST LRO operation until it is done."""
    if "/operations/" in operation_name:
        parts = operation_name.split("/operations/")
        op_id = parts[-1]
        prefix_parts = parts[0].split("/")
        if "projects" in prefix_parts:
            idx = prefix_parts.index("projects")
            if len(prefix_parts) >= idx + 4 and prefix_parts[idx + 2] == "locations":
                operation_name = f"projects/{prefix_parts[idx + 1]}/locations/{prefix_parts[idx + 3]}/operations/{op_id}"
            elif len(prefix_parts) >= idx + 2:
                operation_name = f"projects/{prefix_parts[idx + 1]}/operations/{op_id}"

    url = f"{endpoint}/v1alpha/{operation_name}"
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        response = session.get(url, headers=headers)
        response.raise_for_status()
        op_data = response.json()
        if op_data.get("done"):
            if "error" in op_data:
                raise Exception(f"Operation failed: {op_data['error']}")
            return op_data.get("response")
        time.sleep(5)
    raise TimeoutError(f"Operation {operation_name} timed out after {timeout_seconds} seconds.")

def backup_agent_subresources(session, endpoint, agent_name, agent_dir, headers):
    """Backs up tools, playbooks, and examples for a given agent."""
    agent_id = agent_name.split("/")[-1]
    
    # 1. Backup Tools
    tools_url = f"{endpoint}/v1alpha/{agent_name}/tools"
    print(f"    Checking for Tools under Agent {agent_id}...")
    tools_res = session.get(tools_url, headers=headers)
    tools = []
    if tools_res.status_code == 200:
        tools = tools_res.json().get("tools", [])
        
    tools_backup = []
    if tools:
        os.makedirs(os.path.join(agent_dir, "tools"), exist_ok=True)
        for tool in tools:
            t_name = tool["name"]
            t_id = t_name.split("/")[-1]
            print(f"      Backing up Tool: {t_name}")
            
            t_url = f"{endpoint}/v1alpha/{t_name}"
            t_config = session.get(t_url, headers=headers).json()
            
            local_path = f"gemini_agents/{agent_id}/tools/{t_id}.json"
            with open(os.path.join(agent_dir, "tools", f"{t_id}.json"), "w") as f:
                json.dump(t_config, f, indent=2)
                
            tools_backup.append({
                "tool_id": t_id,
                "display_name": t_config.get("displayName"),
                "local_path": local_path
            })
            
    # 2. Backup Playbooks & Examples
    playbooks_url = f"{endpoint}/v1alpha/{agent_name}/playbooks"
    print(f"    Checking for Playbooks under Agent {agent_id}...")
    playbooks_res = session.get(playbooks_url, headers=headers)
    playbooks = []
    if playbooks_res.status_code == 200:
        playbooks = playbooks_res.json().get("playbooks", [])
        
    playbooks_backup = []
    if playbooks:
        os.makedirs(os.path.join(agent_dir, "playbooks"), exist_ok=True)
        for playbook in playbooks:
            p_name = playbook["name"]
            p_id = p_name.split("/")[-1]
            print(f"      Backing up Playbook: {p_name}")
            
            p_url = f"{endpoint}/v1alpha/{p_name}"
            p_config = session.get(p_url, headers=headers).json()
            
            # Backup Examples under this Playbook
            examples_url = f"{endpoint}/v1alpha/{p_name}/examples"
            examples_res = session.get(examples_url, headers=headers)
            examples = []
            if examples_res.status_code == 200:
                examples = examples_res.json().get("examples", [])
                
            examples_backup = []
            if examples:
                p_examples_dir = os.path.join(agent_dir, "playbooks", p_id, "examples")
                os.makedirs(p_examples_dir, exist_ok=True)
                for example in examples:
                    e_name = example["name"]
                    e_id = e_name.split("/")[-1]
                    print(f"        Backing up Example: {e_name}")
                    
                    e_url = f"{endpoint}/v1alpha/{e_name}"
                    e_config = session.get(e_url, headers=headers).json()
                    
                    local_path = f"gemini_agents/{agent_id}/playbooks/{p_id}/examples/{e_id}.json"
                    with open(os.path.join(p_examples_dir, f"{e_id}.json"), "w") as f:
                        json.dump(e_config, f, indent=2)
                        
                    examples_backup.append({
                        "example_id": e_id,
                        "display_name": e_config.get("displayName"),
                        "local_path": local_path
                    })
                    
            local_path = f"gemini_agents/{agent_id}/playbooks/{p_id}.json"
            with open(os.path.join(agent_dir, "playbooks", f"{p_id}.json"), "w") as f:
                json.dump(p_config, f, indent=2)
                
            playbooks_backup.append({
                "playbook_id": p_id,
                "display_name": p_config.get("displayName"),
                "local_path": local_path,
                "examples": examples_backup
            })
            
    return {
        "tools": tools_backup,
        "playbooks": playbooks_backup
    }

def restore_agent_subresources(session, endpoint, target_agent_name, agent_backup_info, backup_dir, headers):
    """Restores tools, playbooks, and examples for a target agent, updating tool resource names."""
    # 1. Restore Tools
    tool_name_mapping = {}
    tools_backup = agent_backup_info.get("tools", [])
    
    if tools_backup:
        parent_tools_url = f"{endpoint}/v1alpha/{target_agent_name}/tools"
        
        # List existing tools
        existing_tools = []
        res = session.get(parent_tools_url, headers=headers)
        if res.status_code == 200:
            existing_tools = res.json().get("tools", [])
        existing_tool_names = {t.get("displayName"): t.get("name") for t in existing_tools}
        
        for t_info in tools_backup:
            local_path = t_info["local_path"]
            display_name = t_info["display_name"]
            
            with open(os.path.join(backup_dir, local_path), "r") as f:
                t_config = json.load(f)
                
            old_name = t_config.get("name")
            t_config.pop("name", None)
            t_config.pop("createTime", None)
            t_config.pop("updateTime", None)
            
            if display_name in existing_tool_names:
                new_tool_name = existing_tool_names[display_name]
                print(f"      Tool '{display_name}' already exists. Updating via PATCH...")
                patch_url = f"{endpoint}/v1alpha/{new_tool_name}"
                session.patch(patch_url, json=t_config, headers=headers).raise_for_status()
            else:
                print(f"      Creating Tool '{display_name}'...")
                create_res = session.post(parent_tools_url, json=t_config, headers=headers)
                create_res.raise_for_status()
                new_tool_name = create_res.json().get("name")
                
            tool_name_mapping[old_name] = new_tool_name

    # 2. Restore Playbooks
    playbook_name_mapping = {}
    playbooks_backup = agent_backup_info.get("playbooks", [])
    
    if playbooks_backup:
        parent_playbooks_url = f"{endpoint}/v1alpha/{target_agent_name}/playbooks"
        
        # List existing playbooks
        existing_playbooks = []
        res = session.get(parent_playbooks_url, headers=headers)
        if res.status_code == 200:
            existing_playbooks = res.json().get("playbooks", [])
        existing_playbook_names = {p.get("displayName"): p.get("name") for p in existing_playbooks}
        
        for p_info in playbooks_backup:
            local_path = p_info["local_path"]
            display_name = p_info["display_name"]
            
            with open(os.path.join(backup_dir, local_path), "r") as f:
                p_config = json.load(f)
                
            old_name = p_config.get("name")
            
            # Update tool references in playbook steps/configuration
            p_config_str = json.dumps(p_config)
            for old_tool, new_tool in tool_name_mapping.items():
                p_config_str = p_config_str.replace(old_tool, new_tool)
            p_config = json.loads(p_config_str)
            
            p_config.pop("name", None)
            p_config.pop("createTime", None)
            p_config.pop("updateTime", None)
            
            if display_name in existing_playbook_names:
                new_playbook_name = existing_playbook_names[display_name]
                print(f"      Playbook '{display_name}' already exists. Updating via PATCH...")
                patch_url = f"{endpoint}/v1alpha/{new_playbook_name}"
                session.patch(patch_url, json=p_config, headers=headers).raise_for_status()
            else:
                print(f"      Creating Playbook '{display_name}'...")
                create_res = session.post(parent_playbooks_url, json=p_config, headers=headers)
                create_res.raise_for_status()
                new_playbook_name = create_res.json().get("name")
                
            playbook_name_mapping[old_name] = new_playbook_name
            
            # 3. Restore Examples under this Playbook
            examples_backup = p_info.get("examples", [])
            if examples_backup:
                parent_examples_url = f"{endpoint}/v1alpha/{new_playbook_name}/examples"
                
                # List existing examples
                existing_examples = []
                res = session.get(parent_examples_url, headers=headers)
                if res.status_code == 200:
                    existing_examples = res.json().get("examples", [])
                existing_example_names = {e.get("displayName"): e.get("name") for e in existing_examples}
                
                for e_info in examples_backup:
                    e_local_path = e_info["local_path"]
                    e_display_name = e_info["display_name"]
                    
                    with open(os.path.join(backup_dir, e_local_path), "r") as f:
                        e_config = json.load(f)
                        
                    e_config.pop("name", None)
                    e_config.pop("createTime", None)
                    e_config.pop("updateTime", None)
                    
                    if e_display_name in existing_example_names:
                        new_example_name = existing_example_names[e_display_name]
                        print(f"        Example '{e_display_name}' already exists. Updating via PATCH...")
                        patch_url = f"{endpoint}/v1alpha/{new_example_name}"
                        session.patch(patch_url, json=e_config, headers=headers).raise_for_status()
                    else:
                        print(f"        Creating Example '{e_display_name}'...")
                        session.post(parent_examples_url, json=e_config, headers=headers).raise_for_status()

def backup_gemini_agents(session, endpoint, project, location, collection, engine_id, output_dir):
    """Backs up all Gemini Enterprise Agents (assistants/agents) associated with the Engine."""
    url = f"{endpoint}/v1alpha/projects/{project}/locations/{location}/collections/{collection}/engines/{engine_id}/assistants/default_assistant/agents"
    print(f"\nChecking for Gemini Enterprise Agents at: {url}")
    
    headers = {"x-goog-user-project": project}
    response = session.get(url, headers=headers)
    if response.status_code == 404:
        print("  No assistants/agents endpoint found for this Engine type. Skipping.")
        return []
    elif response.status_code != 200:
        print(f"  Warning: Failed to list Gemini agents (status code {response.status_code}). Skipping.")
        return []
        
    agents_data = response.json()
    agents = agents_data.get("agents", [])
    if not agents:
        print("  No Gemini agents found under this Engine.")
        return []
        
    agents_backup = []
    local_agents_dir = os.path.join(output_dir, "gemini_agents")
    os.makedirs(local_agents_dir, exist_ok=True)
    
    for agent in agents:
        agent_name = agent["name"]
        agent_id = agent_name.split("/")[-1]
        print(f"  Backing up Gemini Agent: {agent_name}")
        
        # Get full agent config
        agent_url = f"{endpoint}/v1alpha/{agent_name}"
        agent_response = session.get(agent_url, headers=headers)
        agent_response.raise_for_status()
        agent_config = agent_response.json()
        
        # Save agent config locally
        agent_local_dir = os.path.join(local_agents_dir, agent_id)
        os.makedirs(agent_local_dir, exist_ok=True)
        local_path = f"gemini_agents/{agent_id}/agent_config.json"
        with open(os.path.join(agent_local_dir, "agent_config.json"), "w") as f:
            json.dump(agent_config, f, indent=2)
            
        # Backup sub-resources (tools, playbooks, examples)
        subresources = backup_agent_subresources(session, endpoint, agent_name, agent_local_dir, headers)
            
        agents_backup.append({
            "agent_id": agent_id,
            "display_name": agent_config.get("displayName"),
            "local_path": local_path,
            "tools": subresources["tools"],
            "playbooks": subresources["playbooks"]
        })
        
    return agents_backup

def restore_gemini_agents(backup_dir, target_project, target_location, target_collection, target_engine_id, agents_backup, metadata):
    """Restores Gemini Enterprise Agents from backup to the target Engine."""
    if not agents_backup:
        return
        
    session = get_session()
    
    endpoint = get_rest_endpoint(target_location)
    parent_url = f"{endpoint}/v1alpha/projects/{target_project}/locations/{target_location}/collections/{target_collection}/engines/{target_engine_id}/assistants/default_assistant/agents"
    
    # List existing agents in target
    print(f"\nRestoring Gemini Enterprise Agents to: {parent_url}")
    headers = {"x-goog-user-project": target_project}
    response = session.get(parent_url, headers=headers)
    existing_agents = []
    if response.status_code == 200:
        existing_agents = response.json().get("agents", [])
        
    existing_names = {a.get("displayName"): a.get("name") for a in existing_agents}
    
    for agent_info in agents_backup:
        local_path = agent_info["local_path"]
        display_name = agent_info["display_name"]
        
        local_file_path = os.path.join(backup_dir, local_path)
        if not os.path.exists(local_file_path):
            print(f"  Warning: Backup file for agent '{display_name}' not found at {local_file_path}. Skipping.")
            continue
            
        with open(local_file_path, "r") as f:
            agent_config = json.load(f)
            
        source_project = metadata["project"]
        source_location = metadata["location"]
        source_engine_id = metadata["engine_id"]
        
        # Strip read-only fields
        agent_config.pop("name", None)
        agent_config.pop("createTime", None)
        agent_config.pop("updateTime", None)
        
        if "lowCodeAgentDefinition" in agent_config:
            agent_config["lowCodeAgentDefinition"].pop("session", None)
            
        # Map project, location, and engine IDs in the config
        agent_config_str = json.dumps(agent_config)
        agent_config_str = agent_config_str.replace(f"projects/{source_project}", f"projects/{target_project}")
        agent_config_str = agent_config_str.replace(f"locations/{source_location}", f"locations/{target_location}")
        agent_config_str = agent_config_str.replace(source_engine_id, target_engine_id)
        agent_config = json.loads(agent_config_str)
        
        if display_name in existing_names:
            target_agent_name = existing_names[display_name]
            print(f"  Gemini Agent '{display_name}' already exists in target Engine. Updating via PATCH...")
            patch_url = f"{endpoint}/v1alpha/{target_agent_name}"
            patch_response = session.patch(patch_url, json=agent_config, headers=headers)
            if patch_response.status_code != 200:
                print(f"    Warning: Failed to update agent via PATCH (status {patch_response.status_code}): {patch_response.text}")
            else:
                print(f"    Agent '{display_name}' updated successfully.")
        else:
            print(f"  Creating Gemini Agent '{display_name}' in target Engine...")
            create_response = session.post(parent_url, json=agent_config, headers=headers)
            create_response.raise_for_status()
            target_agent_name = create_response.json().get("name")
            print(f"    Agent '{display_name}' created successfully: {target_agent_name}")
            
        # Restore sub-resources (tools, playbooks, examples)
        print(f"  Restoring sub-resources for Agent '{display_name}'...")
        restore_agent_subresources(session, endpoint, target_agent_name, agent_info, backup_dir, headers)

def backup_engine(project, location, collection, engine_id, output_dir):
    """Backs up a Gemini Enterprise App (Engine) and its assets using the v1alpha REST API."""
    session = get_session()
    endpoint = get_rest_endpoint(location)
    headers = {"x-goog-user-project": project}
    
    # 1. Fetch Engine configuration
    engine_url = f"{endpoint}/v1alpha/projects/{project}/locations/{location}/collections/{collection}/engines/{engine_id}"
    print(f"Fetching Engine: {engine_url}")
    engine_response = session.get(engine_url, headers=headers)
    if engine_response.status_code != 200:
        print(f"Error: Engine '{engine_id}' not found or could not be fetched (status={engine_response.status_code}): {engine_response.text}", file=sys.stderr)
        sys.exit(1)
        
    engine_config = engine_response.json()
    datastores_backup = []
    
    # 2. Process each associated Data Store
    data_store_ids = engine_config.get("dataStoreIds") or engine_config.get("data_store_ids") or []
    for ds_id_path in data_store_ids:
        ds_id = ds_id_path.split("/")[-1]
        ds_url = f"{endpoint}/v1alpha/projects/{project}/locations/{location}/collections/{collection}/dataStores/{ds_id}"
        print(f"\nProcessing Data Store: {ds_id}")
        
        ds_response = session.get(ds_url, headers=headers)
        if ds_response.status_code != 200:
            print(f"Warning: Data Store '{ds_id}' could not be fetched (status={ds_response.status_code}). Skipping.", file=sys.stderr)
            continue
            
        ds_config = ds_response.json()
        
        # Fetch Schema if it exists
        schema_url = f"{ds_url}/schemas/default_schema"
        schema_config = None
        schema_response = session.get(schema_url, headers=headers)
        if schema_response.status_code == 200:
            schema_config = schema_response.json()
            print(f"  Found custom schema for Data Store '{ds_id}'")
        else:
            print(f"  No custom schema found for Data Store '{ds_id}' (using default).")
            
        ds_backup_info = {
            "data_store_id": ds_id,
            "data_store_config": ds_config,
            "schema_config": schema_config,
        }
        datastores_backup.append(ds_backup_info)
        
    # 3. Save backup metadata
    backup_metadata = {
        "engine_id": engine_id,
        "engine_config": engine_config,
        "datastores": datastores_backup,
        "project": project,
        "location": location,
        "collection": collection
    }
    
    # 4. Backup Gemini Enterprise Agents (v1alpha Assistants/Agents)
    try:
        gemini_agents = backup_gemini_agents(session, endpoint, project, location, collection, engine_id, output_dir)
        if gemini_agents:
            backup_metadata["gemini_agents"] = gemini_agents
    except Exception as e:
        print(f"Warning: Failed to backup Gemini Enterprise Agents: {e}", file=sys.stderr)
    
    os.makedirs(output_dir, exist_ok=True)
    metadata_path = os.path.join(output_dir, "backup_metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(backup_metadata, f, indent=2)
        
    print(f"\nBackup completed successfully! Metadata saved to: {metadata_path}")

def restore_engine(backup_dir, target_project, target_location, target_collection):
    """Restores a Gemini Enterprise App (Engine) and its assets from a backup using the v1alpha REST API."""
    session = get_session()
    endpoint = get_rest_endpoint(target_location)
    headers = {"x-goog-user-project": target_project, "Content-Type": "application/json"}
    
    metadata_path = os.path.join(backup_dir, "backup_metadata.json")
    if not os.path.exists(metadata_path):
        print(f"Error: Backup metadata file not found at {metadata_path}", file=sys.stderr)
        sys.exit(1)
        
    with open(metadata_path, "r") as f:
        metadata = json.load(f)
        
    engine_id = metadata["engine_id"]
    engine_config = metadata["engine_config"]
    datastores = metadata["datastores"]
    gemini_agents = metadata.get("gemini_agents", [])
    
    parent_path = f"projects/{target_project}/locations/{target_location}/collections/{target_collection}"
    
    # 1. Recreate Data Stores and Schemas
    recreated_ds_ids = []
    for ds_info in datastores:
        ds_id = ds_info["data_store_id"]
        ds_config = ds_info["data_store_config"]
        schema_config = ds_info["schema_config"]
        
        # Clean up read-only fields
        ds_config.pop("name", None)
        ds_config.pop("createTime", None)
        ds_config.pop("defaultSchemaId", None)
        ds_config.pop("default_schema_id", None)
        
        ds_check_url = f"{endpoint}/v1alpha/{parent_path}/dataStores/{ds_id}"
        print(f"\nChecking Data Store: {ds_id}")
        
        check_response = session.get(ds_check_url, headers=headers)
        if check_response.status_code == 200:
            print(f"  Data Store '{ds_id}' already exists. Skipping creation.")
        else:
            print(f"  Creating Data Store '{ds_id}'...")
            create_ds_url = f"{endpoint}/v1alpha/{parent_path}/dataStores?dataStoreId={ds_id}"
            create_response = session.post(create_ds_url, json=ds_config, headers=headers)
            create_response.raise_for_status()
            
            op_data = create_response.json()
            if op_data and not op_data.get("done") and "name" in op_data and "/operations/" in op_data["name"]:
                print("  Waiting for creation operation to complete...")
                wait_for_operation(session, endpoint, op_data["name"], headers)
            print(f"  Data Store '{ds_id}' created successfully.")
            
        # Recreate Schema if present in backup
        if schema_config:
            schema_check_url = f"{endpoint}/v1alpha/{parent_path}/dataStores/{ds_id}/schemas/default_schema"
            schema_config.pop("name", None)
            
            schema_check_response = session.get(schema_check_url, headers=headers)
            if schema_check_response.status_code == 200:
                print(f"  Schema for '{ds_id}' already exists. Skipping creation.")
            else:
                print(f"  Creating schema for '{ds_id}'...")
                create_schema_url = f"{endpoint}/v1alpha/{parent_path}/dataStores/{ds_id}/schemas?schemaId=default_schema"
                create_schema_response = session.post(create_schema_url, json=schema_config, headers=headers)
                create_schema_response.raise_for_status()
                resp_json = create_schema_response.json()
                if resp_json and not resp_json.get("done") and "name" in resp_json and "/operations/" in resp_json["name"]:
                    print("  Waiting for schema creation operation to complete...")
                    wait_for_operation(session, endpoint, resp_json["name"], headers)
                print(f"  Schema created successfully.")
                
        recreated_ds_ids.append(ds_id)
        
    # 2. Recreate Engine
    engine_check_url = f"{endpoint}/v1alpha/{parent_path}/engines/{engine_id}"
    print(f"\nChecking Engine: {engine_id}")
    
    # Clean up read-only fields
    engine_config.pop("name", None)
    engine_config.pop("createTime", None)
    engine_config.pop("updateTime", None)
    
    # Ensure it links to the restored data stores (support both formats)
    if "dataStoreIds" in engine_config:
        engine_config["dataStoreIds"] = recreated_ds_ids
    if "data_store_ids" in engine_config:
        engine_config["data_store_ids"] = recreated_ds_ids
    
    check_response = session.get(engine_check_url, headers=headers)
    if check_response.status_code == 200:
        print(f"  Engine '{engine_id}' already exists. Skipping creation.")
    else:
        print(f"  Creating Engine '{engine_id}'...")
        create_engine_url = f"{endpoint}/v1alpha/{parent_path}/engines?engineId={engine_id}"
        create_response = session.post(create_engine_url, json=engine_config, headers=headers)
        create_response.raise_for_status()
        
        op_data = create_response.json()
        if op_data and not op_data.get("done") and "name" in op_data and "/operations/" in op_data["name"]:
            print("  Waiting for creation operation to complete...")
            wait_for_operation(session, endpoint, op_data["name"], headers)
        print(f"  Engine '{engine_id}' created successfully.")
        
    # 3. Restore Gemini Enterprise Agents (v1alpha Assistants/Agents)
    if gemini_agents:
        try:
            restore_gemini_agents(backup_dir, target_project, target_location, target_collection, engine_id, gemini_agents, metadata)
        except Exception as e:
            print(f"Warning: Failed to restore Gemini Enterprise Agents: {e}", file=sys.stderr)
        
    print("\nRestore completed successfully!")

def run_interactive():
    """Runs the backup/restore process in interactive mode, prompting the user for input."""
    log_banner("GEMINI ENTERPRISE — BACKUP & RESTORE TOOL")
    
    print(f"{Style.BOLD}Select an action:{Style.RESET}")
    print(f"  {Style.GREEN}[1]{Style.RESET} Backup an App/Engine")
    print(f"  {Style.GREEN}[2]{Style.RESET} Restore an App/Engine from Backup")
    
    action = "1"
    while True:
        choice = input(f"\n{Style.CYAN}Select an option (1 or 2) [1]: {Style.RESET}").strip() or "1"
        if choice in ("1", "2"):
            action = choice
            break

    # Resolve default project
    default_proj = get_default_project()
    
    if action == "1":
        log_banner("BACKUP CONFIGURATION")
        
        # 1. Project Selection
        if default_proj:
            project = input(f"{Style.CYAN}GCP Project ID [{default_proj}]: {Style.RESET}").strip() or default_proj
        else:
            project = input(f"{Style.CYAN}GCP Project ID (required): {Style.RESET}").strip()
            while not project:
                project = input(f"{Style.CYAN}GCP Project ID (required): {Style.RESET}").strip()
                
        # 2. Location Selection
        location = input(f"{Style.CYAN}Location/Region [global]: {Style.RESET}").strip() or "global"
        
        collection = "default_collection"
        
        # 3. Engine Selection
        print(f"\n{Style.BOLD}Fetching available Engines (Apps)...{Style.RESET}")
        session = get_session()
        endpoint = get_rest_endpoint(location)
        list_url = f"{endpoint}/v1alpha/projects/{project}/locations/{location}/collections/{collection}/engines"
        headers = {"x-goog-user-project": project}
        
        discovered_engines = []
        try:
            res = session.get(list_url, headers=headers)
            if res.status_code == 200:
                discovered_engines = res.json().get("engines", [])
        except Exception as e:
            log_warning(f"Could not list engines automatically: {e}")
            
        engine_id = None
        if discovered_engines:
            print(f"\nDiscovered {len(discovered_engines)} Engine(s):")
            for idx, eng in enumerate(discovered_engines, 1):
                disp_name = eng.get("displayName") or eng.get("display_name")
                eng_name = eng.get("name", "")
                eng_id = eng_name.split("/")[-1]
                print(f"  {Style.GREEN}[{idx}]{Style.RESET} {Style.BOLD}{disp_name}{Style.RESET} (ID: {eng_id})")
            print(f"  {Style.GREEN}[0]{Style.RESET} Enter a custom Engine ID manually")
            
            while True:
                try:
                    sel = input(f"\n{Style.CYAN}Select an engine (0-{len(discovered_engines)}): {Style.RESET}").strip()
                    if not sel:
                        continue
                    sel_idx = int(sel)
                    if 0 <= sel_idx <= len(discovered_engines):
                        if sel_idx > 0:
                            eng_name = discovered_engines[sel_idx - 1].get("name", "")
                            engine_id = eng_name.split("/")[-1]
                        break
                    else:
                        print(f"Please enter a number between 0 and {len(discovered_engines)}")
                except ValueError:
                    print("Invalid input. Please enter a valid number.")
                    
        if not engine_id:
            engine_id = input(f"{Style.CYAN}Enter Engine (App) ID manually: {Style.RESET}").strip()
            while not engine_id:
                engine_id = input(f"{Style.CYAN}Enter Engine (App) ID manually: {Style.RESET}").strip()
                
        # 4. Output Directory
        default_dir = f"./backup-{engine_id}"
        output_dir = input(f"{Style.CYAN}Local output directory [{default_dir}]: {Style.RESET}").strip() or default_dir
        
        # Confirm & Run
        print(f"\n{Style.BOLD}Ready to start backup with the following settings:{Style.RESET}")
        print(f"  Project:    {Style.GREEN}{project}{Style.RESET}")
        print(f"  Location:   {Style.GREEN}{location}{Style.RESET}")
        print(f"  Engine ID:  {Style.GREEN}{engine_id}{Style.RESET}")
        print(f"  Output Dir: {Style.GREEN}{output_dir}{Style.RESET}")
        
        confirm = input(f"\n{Style.CYAN}Proceed with backup? (Y/n): {Style.RESET}").strip().lower() or 'y'
        if confirm != 'y':
            log_info("Backup cancelled.")
            sys.exit(0)
            
        backup_engine(
            project=project,
            location=location,
            collection=collection,
            engine_id=engine_id,
            output_dir=output_dir,
        )
        
    elif action == "2":
        log_banner("RESTORE CONFIGURATION")
        
        # 1. Backup Directory
        backup_dir = input(f"{Style.CYAN}Enter local backup directory: {Style.RESET}").strip()
        while not backup_dir or not os.path.exists(backup_dir):
            if backup_dir and not os.path.exists(backup_dir):
                log_error(f"Directory '{backup_dir}' does not exist.")
            backup_dir = input(f"{Style.CYAN}Enter local backup directory: {Style.RESET}").strip()
            
        # 2. Target Project
        if default_proj:
            project = input(f"{Style.CYAN}Target GCP Project ID [{default_proj}]: {Style.RESET}").strip() or default_proj
        else:
            project = input(f"{Style.CYAN}Target GCP Project ID (required): {Style.RESET}").strip()
            while not project:
                project = input(f"{Style.CYAN}Target GCP Project ID (required): {Style.RESET}").strip()
                
        # 3. Target Location
        location = input(f"{Style.CYAN}Target Location/Region [global]: {Style.RESET}").strip() or "global"
        
        collection = "default_collection"
        
        # Confirm & Run
        print(f"\n{Style.BOLD}Ready to start restore with the following settings:{Style.RESET}")
        print(f"  Backup Dir:    {Style.GREEN}{backup_dir}{Style.RESET}")
        print(f"  Target Project:{Style.GREEN}{project}{Style.RESET}")
        print(f"  Target Loc:    {Style.GREEN}{location}{Style.RESET}")
            
        confirm = input(f"\n{Style.CYAN}Proceed with restore? (Y/n): {Style.RESET}").strip().lower() or 'y'
        if confirm != 'y':
            log_info("Restore cancelled.")
            sys.exit(0)
            
        restore_engine(
            backup_dir=backup_dir,
            target_project=project,
            target_location=location,
            target_collection=collection,
        )

def main():
    parser = argparse.ArgumentParser(description="Backup and Restore tool for Gemini Enterprise / Discovery Engine Apps.")
    parser.add_argument("-i", "--interactive", action="store_true", help="Run the tool in interactive mode")
    
    subparsers = parser.add_subparsers(dest="command")
    
    # Backup parser
    backup_parser = subparsers.add_parser("backup", help="Backup an Engine and its assets.")
    backup_parser.add_argument("--project", required=True, help="Google Cloud Project ID")
    backup_parser.add_argument("--location", default="global", help="GCP Location (default: global)")
    backup_parser.add_argument("--collection", default="default_collection", help="Discovery Engine Collection ID (default: default_collection)")
    backup_parser.add_argument("--engine", required=True, help="Engine (App) ID to backup")
    backup_parser.add_argument("--output-dir", required=True, help="Local directory to save metadata and downloaded backups")
    
    # Restore parser
    restore_parser = subparsers.add_parser("restore", help="Restore an Engine and its assets from a backup.")
    restore_parser.add_argument("--backup-dir", required=True, help="Local directory containing the backup_metadata.json and assets")
    restore_parser.add_argument("--project", required=True, help="Target Google Cloud Project ID")
    restore_parser.add_argument("--location", default="global", help="Target GCP Location (default: global)")
    restore_parser.add_argument("--collection", default="default_collection", help="Target Discovery Engine Collection ID (default: default_collection)")
    
    args = parser.parse_args()
    
    # If interactive flag is passed, or if no command is specified, run in interactive mode
    if args.interactive or not args.command:
        run_interactive()
    else:
        if args.command == "backup":
            backup_engine(
                project=args.project,
                location=args.location,
                collection=args.collection,
                engine_id=args.engine,
                output_dir=args.output_dir,
            )
        elif args.command == "restore":
            restore_engine(
                backup_dir=args.backup_dir,
                target_project=args.project,
                target_location=args.location,
                target_collection=args.collection,
            )

if __name__ == "__main__":
    main()
