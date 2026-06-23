"""假说包：注释传递(相似邻居母蛋白属性 → 共识 → 预测属性)。"""
from pkg.hypothesis.base import Neighbor, Prediction
from pkg.hypothesis.propagate import transfer_annotations

__all__ = ["Neighbor", "Prediction", "transfer_annotations"]
