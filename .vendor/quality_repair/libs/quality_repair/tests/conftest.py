import sys
from pathlib import Path

# 允许从仓库根目录以 libs.quality_repair 导入
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
