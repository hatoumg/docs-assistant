You are grading an answer from a document question-answering system.

You are given the question, the reference answer written by a person, the passages the system retrieved, and the system's answer. Score each criterion 0, 1 or 2.

correctness
- 0: wrong or missing
- 1: partly right or incomplete
- 2: matches the reference answer

faithfulness
- 0: contains claims that the passages do not support
- 1: one minor detail is not supported by the passages
- 2: every claim is supported by the passages

citation
- 0: no citation, or the cited passages do not support the answer
- 1: cites the right document but not the best passage
- 2: the cited passages support the answer

Reply with JSON only, no other text, in exactly this form:
{"correctness": 0, "faithfulness": 0, "citation": 0, "reason": "one short sentence"}

Question: {{question}}

Reference answer: {{reference}}

Retrieved passages:
{{passages}}

System answer: {{answer}}
