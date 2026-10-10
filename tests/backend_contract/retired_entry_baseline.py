from __future__ import annotations

def update_plc_config(request: PlcConfigRequest) -> dict[str, Any]:
    return _plc_config_diagnostics.update(request)
    request_payload = plc_config_request_payload(request)
    request_fields = set(request_payload)
    legacy_fields = {"d206_address", "y04_address", "write_y04"}
    v2_fields = {"result_register", "output_control_point", "capture_trigger_enabled", "capture_input_register", "capture_trigger_value"}
    if request_fields & legacy_fields and request_fields & v2_fields:
        raise HTTPException(status_code=400, detail="legacy and v2 PLC address fields cannot be mixed")
    legacy_replacement = request_fields == PLC_LEGACY_IO_CONFIG_FIELDS
    if request_fields & legacy_fields and not legacy_replacement:
        raise HTTPException(status_code=400, detail="legacy PLC fields require a complete legacy configuration payload")
    full_replacement = request_fields == PLC_IO_CONFIG_FIELDS or legacy_replacement

    def mutate(config: dict[str, Any]) -> None:
        current_raw = raw_plc_namespace(config)
        if not full_replacement and current_raw is not PLC_CONFIG_ABSENT and not isinstance(current_raw, dict):
            raise PlcConfigError("malformed plc namespace requires a complete legal replacement")
        current = current_raw if isinstance(current_raw, dict) else {}
        if full_replacement:
            candidate = dict(request_payload)
        else:
            current = normalize_plc_config(current_raw)
            candidate = {**current, **request_payload}
        normalized_candidate = normalize_plc_config(candidate)
        activation_errors = plc_activation_errors(normalized_candidate)
        if activation_errors:
            raise PlcConfigError(activation_errors[0]["code"])
        try:
            normalized_current = normalize_plc_config(current_raw)
        except PlcConfigError:
            normalized_current = None
        config["plc"] = normalized_candidate
        if normalized_current != normalized_candidate:
            config[PLC_CONTROL_GENERATION_KEY] = int(config.get(PLC_CONTROL_GENERATION_KEY) or 0) + 1

    try:
        config = mutate_app_config_atomically(mutate)
    except PlcConfigError as exc:
        status_code = 409 if str(exc).startswith("plc_") and str(exc).endswith(("_unavailable", "_missing", "_unverified")) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    return plc_config_response(config)


def claim_plc_capture_session(request: PlcCaptureSessionRequest) -> dict[str, Any]:
    raise HTTPException(status_code=410, detail="legacy_plc_input_capture_is_read_only")
    if request.camera_ready is not True:
        raise HTTPException(status_code=409, detail="camera_not_ready")
    model_id = str(request.model_id or "").strip()
    require_analyze_model_permission(model_id or None)
    user = current_auth_user()
    config = load_config()
    try:
        settings = normalize_plc_config(raw_plc_namespace(config))
    except PlcConfigError as exc:
        raise HTTPException(status_code=409, detail="plc_config_invalid") from exc
    if not settings["enabled"] or not settings["capture_trigger_enabled"] or plc_activation_errors(settings):
        raise HTTPException(status_code=409, detail="plc_capture_not_effective")
    try:
        return plc_claim_capture_session(str(user.get("id") or ""), model_id)
    except PlcConfigError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def heartbeat_plc_capture_session(request: PlcCaptureSessionHeartbeatRequest) -> dict[str, Any]:
    raise HTTPException(status_code=410, detail="legacy_plc_input_capture_is_read_only")
    user = current_auth_user()
    config = load_config()
    try:
        settings = normalize_plc_config(raw_plc_namespace(config))
    except PlcConfigError as exc:
        raise HTTPException(status_code=409, detail="plc_config_invalid") from exc
    if not settings["enabled"] or not settings["capture_trigger_enabled"] or plc_activation_errors(settings):
        raise HTTPException(status_code=409, detail="plc_capture_not_effective")
    try:
        renewed = plc_heartbeat_capture_session(request.session_id.strip(), str(user.get("id") or ""))
        require_analyze_model_permission(str(renewed.get("model_id") or "") or None)
        return renewed
    except PlcConfigError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def release_plc_capture_session(session_id: str) -> dict[str, Any]:
    raise HTTPException(status_code=410, detail="legacy_plc_input_capture_is_read_only")
    user = current_auth_user()
    plc_release_capture_session(session_id.strip(), str(user.get("id") or ""))
    return {"released": True}


def stream_plc_capture_events(session_id: str) -> StreamingResponse:
    raise HTTPException(status_code=410, detail="legacy_plc_input_capture_is_read_only")
    user_id = str(current_auth_user().get("id") or "")
    clean_session_id = session_id.strip()
    if not clean_session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    def event_stream() -> Any:
        deadline = time.monotonic() + 15.0
        last_heartbeat = 0.0
        while time.monotonic() < deadline:
            try:
                event = plc_claim_next_capture_event(clean_session_id, user_id)
            except PlcConfigError:
                yield "event: session_expired\ndata: {}\n\n"
                return
            if event is not None:
                payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                yield f"id: {event['trigger_id']}\nevent: capture\ndata: {payload}\n\n"
            now = time.monotonic()
            if now - last_heartbeat >= 5.0:
                yield ": keepalive\n\n"
                last_heartbeat = now
            time.sleep(PLC_CAPTURE_POLL_SECONDS)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def update_ai_config(request: AiConfigRequest) -> dict[str, Any]:
    require_admin_role()
    raise HTTPException(409, "请使用模型与 API 配置库；旧配置入口已停用")
    local = load_ai_local_config()
    if request.provider is not None:
        next_provider = validate_ai_provider(request.provider)
        provider_changed = str(local.get("provider") or "").strip().lower() != next_provider
        local["provider"] = next_provider
        if provider_changed and request.model is None:
            local["model"] = default_ai_model(next_provider)
        if provider_changed and request.base_url is None:
            local["base_url"] = default_ai_base_url(next_provider)
        if provider_changed and request.api_key_env is None:
            local["api_key_env"] = "DASHSCOPE_API_KEY" if next_provider == "qwen" else "GEMINI_API_KEY"
    if request.model is not None:
        local["model"] = validate_ai_model(request.model)
    if request.base_url is not None:
        local["base_url"] = validate_ai_base_url(request.base_url)
    if request.proxy_url is not None:
        local["proxy_url"] = validate_ai_proxy_url(request.proxy_url)
    if request.auto_local_proxy is not None:
        local["auto_local_proxy"] = bool(request.auto_local_proxy)
    if request.api_key_env is not None:
        local["api_key_env"] = validate_ai_key_env(request.api_key_env)
    timeout_value = request.timeout_seconds if request.timeout_seconds is not None else request.timeout
    if timeout_value is not None:
        local["timeout_seconds"] = validate_ai_timeout(timeout_value)
    if request.api_key is not None and request.api_key.strip():
        secret = request.api_key.strip()
        key_provider = validate_ai_provider(local.get("provider") or AI_DEFAULT_PROVIDER)
        env_name = validate_ai_key_env(request.api_key_env) or default_secret_env_name("VANTALINE_AI_KEY", secret, provider=key_provider)
        set_local_secret_env(env_name, secret)
        key_items = normalize_ai_key_items(local, key_provider)
        item_id = secret_key_item_id(env_name, secret)
        existing = next((item for item in key_items if item["id"] == item_id and item.get("provider") == key_provider), None)
        if existing:
            existing["key"] = secret
            existing["env"] = env_name
            existing["provider"] = key_provider
        else:
            key_items.append(
                {
                    "id": item_id,
                    "label": f"{ai_provider_label(key_provider)} API Key",
                    "key": secret,
                    "env": env_name,
                    "provider": key_provider,
                }
            )
        local["api_keys"] = key_items
        local["active_key_id"] = item_id
    if request.active_key_id is not None:
        active_key_id = request.active_key_id.strip()
        key_provider = validate_ai_provider(local.get("provider") or AI_DEFAULT_PROVIDER)
        current_keys = ai_keys_for_provider(normalize_ai_key_items(local, key_provider), key_provider)
        if active_key_id and not any(item["id"] == active_key_id for item in current_keys):
            raise HTTPException(status_code=400, detail="AI active_key_id was not found")
        local["active_key_id"] = active_key_id
    if request.image_provider is not None:
        local["image_provider"] = validate_image_generation_provider(request.image_provider)
        if request.image_model is None:
            local["image_model"] = default_image_generation_model(local["image_provider"])
        if request.image_base_url is None:
            local["image_base_url"] = default_image_generation_base_url(local["image_provider"])
    if request.image_model is not None:
        local["image_model"] = validate_ai_model(request.image_model)
    if request.image_base_url is not None:
        local["image_base_url"] = validate_ai_base_url(request.image_base_url)
    if request.image_timeout_seconds is not None:
        local["image_timeout_seconds"] = validate_image_generation_timeout(request.image_timeout_seconds)
    if request.image_api_key_env is not None:
        local["image_api_key_env"] = validate_ai_key_env(request.image_api_key_env)
    if request.image_api_key is not None and request.image_api_key.strip():
        secret = request.image_api_key.strip()
        image_provider = validate_image_generation_provider(local.get("image_provider") or IMAGE_GENERATION_DEFAULT_PROVIDER)
        env_name = (
            validate_ai_key_env(request.image_api_key_env)
            or default_secret_env_name(f"VANTALINE_{image_provider.upper()}_IMAGE_KEY", secret, provider=image_provider)
        )
        set_local_secret_env(env_name, secret)
        key_items = normalize_image_key_items(local, image_provider)
        item_id = secret_key_item_id(env_name, secret)
        existing = next((item for item in key_items if item["id"] == item_id and item.get("provider") == image_provider), None)
        if existing:
            existing["key"] = secret
            existing["env"] = env_name
        else:
            key_items.append(
                {
                    "id": item_id,
                    "label": f"{image_generation_provider_label(image_provider)} API Key",
                    "key": secret,
                    "provider": image_provider,
                    "env": env_name,
                }
            )
        local["image_api_keys"] = key_items
        local["image_active_key_id"] = item_id
    if request.image_active_key_id is not None:
        active_key_id = request.image_active_key_id.strip()
        image_provider = validate_image_generation_provider(local.get("image_provider") or IMAGE_GENERATION_DEFAULT_PROVIDER)
        image_keys = image_keys_for_provider(normalize_image_key_items(local, image_provider), image_provider)
        if active_key_id and not any(item["id"] == active_key_id for item in image_keys):
            raise HTTPException(status_code=400, detail="Image generation active_key_id was not found")
        local["image_active_key_id"] = active_key_id

    local["provider"] = validate_ai_provider(local.get("provider"))
    local["model"] = validate_ai_model(local.get("model") or default_ai_model(local["provider"]))
    local["base_url"] = validate_ai_base_url(local.get("base_url") or default_ai_base_url(local["provider"]))
    local["proxy_url"] = validate_ai_proxy_url(local.get("proxy_url"))
    local["auto_local_proxy"] = bool(local.get("auto_local_proxy", True))
    local["timeout_seconds"] = validate_ai_timeout(local.get("timeout_seconds"))
    local["api_key_env"] = validate_ai_key_env(local.get("api_key_env"))
    local["api_keys"] = persist_secret_key_items(normalize_ai_key_items(local, local["provider"]), "VANTALINE_AI_KEY")
    current_ai_keys = ai_keys_for_provider(local["api_keys"], local["provider"])
    if local.get("active_key_id") and not any(item["id"] == local["active_key_id"] for item in current_ai_keys):
        local["active_key_id"] = ""
    if not local.get("active_key_id") and current_ai_keys:
        local["active_key_id"] = current_ai_keys[0]["id"]
    local["api_key"] = ""
    local["image_provider"] = validate_image_generation_provider(local.get("image_provider") or IMAGE_GENERATION_DEFAULT_PROVIDER)
    local["image_model"] = validate_ai_model(local.get("image_model") or default_image_generation_model(local["image_provider"]))
    local["image_base_url"] = validate_ai_base_url(local.get("image_base_url") or default_image_generation_base_url(local["image_provider"]))
    local["image_timeout_seconds"] = validate_image_generation_timeout(local.get("image_timeout_seconds") or IMAGE_GENERATION_DEFAULT_TIMEOUT_SECONDS)
    local["image_api_key_env"] = validate_ai_key_env(local.get("image_api_key_env"))
    local["image_api_keys"] = persist_secret_key_items(
        normalize_image_key_items(local, local["image_provider"]),
        f"VANTALINE_{local['image_provider'].upper()}_IMAGE_KEY",
    )
    current_image_keys = image_keys_for_provider(local["image_api_keys"], local["image_provider"])
    if local.get("image_active_key_id") and not any(item["id"] == local["image_active_key_id"] for item in current_image_keys):
        local["image_active_key_id"] = ""
    if not local.get("image_active_key_id") and current_image_keys:
        local["image_active_key_id"] = current_image_keys[0]["id"]
    local["image_api_key"] = ""
    save_ai_local_config(local)
    return public_ai_detection_status()


def delete_ai_config_key() -> dict[str, Any]:
    require_admin_role()
    raise HTTPException(409, "请在模型配置库管理 Key")
    local = load_ai_local_config()
    provider = validate_ai_provider(local.get("provider") or AI_DEFAULT_PROVIDER)
    active_key_id = str(local.get("active_key_id") or "").strip()
    key_items = normalize_ai_key_items(local, provider)
    current_keys = ai_keys_for_provider(key_items, provider)
    if active_key_id:
        active_item = next((item for item in current_keys if item["id"] == active_key_id), None)
        if active_item:
            delete_local_secret_env(active_item.get("env") or active_item.get("env_name") or "")
    remaining = [
        item
        for item in key_items
        if not (active_key_id and item["id"] == active_key_id and str(item.get("provider") or "").strip().lower() == provider)
    ]
    local["api_keys"] = persist_secret_key_items(remaining, "VANTALINE_AI_KEY")
    current_remaining = ai_keys_for_provider(local["api_keys"], provider)
    local["active_key_id"] = current_remaining[0]["id"] if current_remaining else ""
    local["api_key"] = ""
    save_ai_local_config(local)
    return public_ai_detection_status()
