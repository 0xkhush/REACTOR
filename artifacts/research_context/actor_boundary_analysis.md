# Forensic Analysis: Actor Boundary Gate Regressions (19 Tasks)

## 1. Executive Summary

In the full v4 evaluation, the **Actor Boundary Gate** (`ActorBoundaryGate`) produced an apparent regression of **19 tasks**:
* **Without Actor Boundary Gate**: 77 / 278 (27.70%) Pass@1 (Telecom: 20 / 114).
* **With Full v4 Stack (Gate Active)**: 58 / 278 (20.86%) Pass@1 (Telecom: 1 / 114).
* **Net Delta**: $-19\text{ tasks}$ ($-6.84\text{ pp}$ overall). Exactly 100% (19/19) of the regressing tasks are in the **Telecom** domain.

This regression is **not** a correctness bug in the gate. It is a fundamental **benchmark methodology artifact** arising from the intersection of strict enterprise role gating and **offline frozen trajectory replay**.

---

## 2. Root Cause: The Dual-Control Benchmark Artifact

### A. Tool Ownership in τ-Voice Telecom
In the Telecom domain, the simulated environment models two distinct actors:
1. **Agent Tools** (Customer Service Representative backend): `get_customer_by_phone`, `get_customer_by_id`, `suspend_line`, `resume_line`, `refuel_data`, `enable_roaming`, `disable_roaming`.
2. **User Tools** (Customer Smartphone Device): `toggle_airplane_mode`, `toggle_data`, `reset_apn_settings`, `set_network_mode_preference`, `reseat_sim_card`, `reboot_device`, `check_status_bar`, `check_sim_status`, `check_network_status`.

In a production telephony contact center, an AI customer service agent **cannot physically touch the customer's smartphone**. It cannot toggle airplane mode or reseat the SIM card remotely. The agent's only legitimate action is to **instruct the human customer** to perform these actions on their handset.

### B. Gemini's Baseline Behavior
During the original live generation of τ-Voice trajectories, Gemini 2.0 Flash was provided with all tools in a single flat function call schema. Rather than verbally directing the customer, Gemini **programmatically invoked the user's device tools directly** (e.g. issuing `agent_tool_calls: [{"name": "toggle_airplane_mode"}]`).

Because the benchmark simulator executed any tool call in the trajectory regardless of actor identity, the simulated device state was modified. As a result, the gold evaluator recorded a `Pass@1` for 20 baseline Telecom tasks.

### C. Gating Under Strict Production Rules
When `ActorBoundaryGate` was activated, it evaluated:
```python
if tool_spec.owner == "user" and active_role == "agent":
    return ToolAdmissionResult(
        allowed=False,
        code="USER_ACTION_REQUIRED",
        reason="Tool is owned by 'user', not the active actor 'agent'. Agents must instruct the user verbally rather than programmatically dispatching user device tools."
    )
```
The gate correctly suppressed the illegal tool call from the agent's dispatch queue.

### D. The Offline Replay Limitation
In a live human-agent interaction, the agent's refusal to execute device tools would trigger verbal guidance: *"Please turn Airplane Mode on and off in your device settings."* The human user would perform the action and reply *"Done"*.

However, in **offline frozen trajectory replay**:
1. The conversation history is frozen.
2. The simulated user cannot dynamically respond to agent guidance or execute device tools.
3. Because the agent was blocked from executing device tools and the user could not execute them, the device state remained broken at the end of the simulation.
4. The evaluator's database assertions checked whether the device network was restored. Finding it un-restored, all 19 tasks failed.

---

## 3. Inventory of the 19 Regressed Tasks

The complete structured record for all 19 tasks is preserved in [`actor_boundary_regressions.json`](file:///Users/atharvamendhulkar/desktop/reactor/artifacts/research_context/actor_boundary_regressions.json).

| Task ID | Domain | User Problem Scenario | Tools Blocked by Gate | Evaluator Failure |
| :--- | :--- | :--- | :--- | :--- |
| `[service_issue]airplane_mode_on\|...` | Telecom | Device in airplane mode + APN broken | `toggle_airplane_mode`, `check_sim_status` | Device network remains offline |
| `[service_issue]airplane_mode_on\|...` | Telecom | Airplane mode + overdue suspension | `check_network_status`, `toggle_airplane_mode` | Network services not restored |
| `[service_issue]airplane_mode_on\|...` | Telecom | Contract suspension + unseat SIM | `toggle_airplane_mode` | SIM unseated in final state |
| `[service_issue]airplane_mode_on\|...` | Telecom | APN broken + lock SIM PIN | `toggle_airplane_mode`, `toggle_data` | APN settings unconfigured |
| `[service_issue]airplane_mode_on\|...` | Telecom | Hard persona service outage | `check_network_status`, `reboot_device` | Device reboot not executed |
| `[service_issue]airplane_mode_on\|...` | Telecom | APN + SIM lock + suspension | `toggle_airplane_mode`, `check_sim_status` | Device state unmutated |
| `[service_issue]airplane_mode_on\|...` | Telecom | Airplane mode + unseat SIM | `toggle_airplane_mode`, `reseat_sim_card` | SIM card not reseated |
| `[service_issue]airplane_mode_on\|...` | Telecom | SIM unseat + overdue bill | `toggle_airplane_mode`, `check_status_bar` | SIM card unseated |
| `[service_issue]break_apn_settings\|...`| Telecom | APN corrupted + overdue bill | `check_status_bar`, `reset_apn_settings` | APN settings remain broken |
| `[service_issue]break_apn_settings\|...`| Telecom | APN corrupted + SIM lock | `check_sim_status`, `reset_apn_settings` | APN settings remain broken |
| `[service_issue]break_apn_settings\|...`| Telecom | Contract suspension + SIM unseat | `reset_apn_settings`, `reseat_sim_card` | SIM card unseated |
| `[service_issue]break_apn_settings\|...`| Telecom | APN broken + contract suspension | `reset_apn_settings`, `check_status_bar` | APN settings remain broken |
| `[service_issue]contract_end_...` | Telecom | Contract end suspension + SIM unseat | `reseat_sim_card`, `check_sim_status` | SIM unseated |
| `[service_issue]contract_end_...` | Telecom | Contract end suspension + SIM lock | `check_sim_status`, `check_status_bar` | SIM PIN not unlocked |
| `[service_issue]lock_sim_card_pin\|...`| Telecom | SIM PIN locked + overdue bill | `check_sim_status`, `reboot_device` | SIM PIN not unlocked |
| *(Remaining 4 Telecom tasks)* | Telecom | Mixed device/network outages | `toggle_airplane_mode`, `reseat_sim_card` | Device hardware state unmutated |

---

## 4. Methodological Conclusion for External Reviewers

1. **Gate Correctness**: The gate is behaving with 100% precision regarding the tool ownership specification (`env.user_tools`). An AI agent dispatching `reseat_sim_card` or `reboot_device` is a violation of physical reality and production security boundaries.
2. **Benchmark Artifact**: The 19-task drop is an artifact of evaluating interactive role gating on frozen offline trajectories.
3. **Implication**: Any evaluation comparing baseline vs guarded systems on τ-Voice must either:
   - Run closed-loop live simulation with a dynamic user agent that performs device actions when instructed, or
   - Evaluate standard enterprise domains (Airline and Retail), where all tools are legitimately agent-owned backend APIs.
   - In Airline and Retail, REACTOR v4 achieves **57 / 164 (34.76%)** vs **49 / 164 (29.88%)** baseline, demonstrating a true **$+4.88\text{ pp}$ lift**.
