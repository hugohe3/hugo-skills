# BPMN 2.0

创建或编辑 `.bpmn`、`.bpmn20.xml` 文件时读取本参考。BPMN 只用于需要标准业务流程语义的场景；普通流程说明优先使用 Mermaid 或 Draw.io。

## 文档结构

```xml
<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions
  xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
  xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
  id="Definitions_Order"
  targetNamespace="https://example.com/bpmn">
  <bpmn:process id="Process_Order" name="订单处理" isExecutable="false">
    <bpmn:startEvent id="Start_Order" name="收到订单"/>
    <bpmn:task id="Task_Review" name="审核订单"/>
    <bpmn:endEvent id="End_Order" name="处理完成"/>
    <bpmn:sequenceFlow id="Flow_Start_Review" sourceRef="Start_Order" targetRef="Task_Review"/>
    <bpmn:sequenceFlow id="Flow_Review_End" sourceRef="Task_Review" targetRef="End_Order"/>
  </bpmn:process>
  <bpmndi:BPMNDiagram id="Diagram_Order">
    <bpmndi:BPMNPlane id="Plane_Order" bpmnElement="Process_Order">
      <!-- BPMNShape and BPMNEdge layout data -->
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>
```

## 语义要求

- 开始/结束用事件，工作用 task 或其专用子类型，分支与汇合用 gateway，不用普通矩形冒充。
- 同一 process 内顺序使用 `sequenceFlow`；不同 participant 间通信使用 `messageFlow`，不要跨池使用顺序流。
- 泳道只表达真实参与者或职责边界，任务必须放入正确 lane。
- 排他、并行和包容网关语义不同；分支条件应写在 outgoing sequence flow 上。
- 每个元素使用稳定唯一 ID，所有 `sourceRef`、`targetRef`、`bpmnElement` 和 lane 引用必须存在。

## 图形信息

可交付 BPMN 文件必须包含 BPMN DI：

- 每个可见节点对应 `bpmndi:BPMNShape` 和 `dc:Bounds`。
- 每条可见连接对应 `bpmndi:BPMNEdge` 和至少两个 `di:waypoint`。
- 布局从左到右，主路径保持水平；异常、补偿或边界事件路径放在主路径之外。

仅有流程语义、没有 DI 的 XML 可能被工具解析，但无法稳定呈现，不作为完整交付物。

## 验证

先运行离线校验器，再用支持 BPMN 2.0 的本地建模器导入并重新打开文件。检查流程语义、网关配对、泳道归属、DI 引用和所有连线端点。不要把私密业务流程上传到公共在线建模器。
