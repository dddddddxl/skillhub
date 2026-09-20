# Experimental HCU testing skills

Private evaluation prototypes, not admitted to the public catalog. Product-source location and maintenance ownership remain to be selected before publication. The official catalog and admission policy remain unchanged.

Original implementation under the parent SkillHub Apache-2.0 license. Workflow inspiration: https://github.com/Ascend/agent-skills at commit 155ac37bd169ddb89479af528297cfb2237400aa, particularly analyse-coverage, generate-unit-test and run-mindspeed-llm-test. No upstream source code, prompt text, or copied third-party manuals are bundled.

The bundled tests validate reporting logic, small PyTorch HCU operations, and a bounded SGLang integration described in VALIDATION_SGLANG.md. They do not certify full SGLang or vLLM model serving, multi-device execution, DTK compatibility across versions, or agent-runtime discovery. Real upstream regression triage is deferred until comparable successful/failed run manifests are available.
