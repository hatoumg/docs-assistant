# Test documents

Check each source's license before copying files into the repo. When unsure, commit a download script instead of the files.

| Set | Source and link | License | In the repo? | Downloaded |
| --- | --- | --- | --- | --- |
| 1. Technical docs | FastAPI tutorial docs, 5 files. https://github.com/fastapi/fastapi (path `docs/en/docs/tutorial`) | MIT | Yes, `data/samples/technical/` (see SOURCE.md) | 2026-10-21 |
| 2. Business contracts | CUAD, 510 commercial contracts from SEC EDGAR. Kaggle: https://www.kaggle.com/datasets/theatticusproject/atticus-open-contract-dataset-aok-beta . Hugging Face: https://huggingface.co/datasets/theatticusproject/cuad-qa . GitHub: https://github.com/TheAtticusProject/cuad/ . Project page: https://www.atticusprojectai.org/cuad . Paper: https://arxiv.org/abs/2103.06268 | CC BY 4.0 (confirm on the Kaggle page) | A few contracts only, plus a download script | |
| 3. Own files | Resume, project READMEs, notes | Private | No | |
| 4. Public policy (optional) | open.canada.ca publications. https://open.canada.ca | Open Government Licence - Canada (confirm per item) | Download script only | |
| 5. Long narrative (optional) | Project Gutenberg. https://www.gutenberg.org | Public domain in the US (confirm per book) | Download script only | |
| 6. Research papers (optional) | arXiv papers marked CC BY. https://arxiv.org | Per paper | Download script only | |

## Attribution

- FastAPI documentation, Copyright (c) 2018 Sebastian Ramirez, MIT license.
- CUAD, Hendrycks, Burns, Chen and Ball, The Atticus Project, CC BY 4.0. Credit this in the README when contracts are used.

Files fetched by the download script go in `data/raw/`, which is git-ignored.

Other candidates not yet checked: ContractNLI (https://arxiv.org/abs/2110.01799) and the Material Contracts Corpus (https://arxiv.org/abs/2504.02864).
