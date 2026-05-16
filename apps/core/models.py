from django.db import models
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db import connection
from django.utils import timezone

# Create your models here.
class QAR(models.Model):
    qar_id = models.CharField('QAR ID', max_length=60, null=True, db_index=True)
    dSimTime = models.FloatField('模拟时间', null=True)
    dStepTime = models.FloatField('单步运行模拟时间', null=True)
    dGravityAcc = models.FloatField('重力加速度', null=True)
    dUwg = models.FloatField('风速沿地轴X轴的分量', null=True)
    dVwg = models.FloatField('风速沿地轴Y轴的分量', null=True)
    dWwg = models.FloatField('风速沿地轴Z轴的分量', null=True)
    dUTrub = models.FloatField('紊流沿机体轴X轴的分量', null=True)
    dVTrub = models.FloatField('紊流沿机体轴Y轴的分量', null=True)
    dWTrub = models.FloatField('紊流沿机体轴Z轴的分量', null=True)
    dMass = models.FloatField('飞机质量', null=True)
    dAlpha = models.FloatField('迎角', null=True)
    dAlphaRad = models.FloatField('迎角', null=True)
    dSinAlpha = models.FloatField('迎角正弦值', null=True)
    dCosAlpha = models.FloatField('迎角余弦值', null=True)
    dAlphaDot = models.FloatField('迎角变化率', null=True)
    dBeta = models.FloatField('侧滑角', null=True)
    dBetaRad = models.FloatField('侧滑角', null=True)
    dSinBeta = models.FloatField('侧滑角正弦值', null=True)
    dCosBeta = models.FloatField('侧滑角余弦值', null=True)
    dBetaDot = models.FloatField('侧滑角变化率', null=True)
    dPhi = models.FloatField('滚转角', null=True)
    dTheta = models.FloatField('俯仰角', null=True)
    dPsi = models.FloatField('偏航角', null=True)
    dChi = models.FloatField('航迹方位角', null=True)
    dGamma = models.FloatField('航迹爬升角', null=True)
    dGroundspeed = models.FloatField('航迹速度', null=True)
    dTAS = models.FloatField('真空速', null=True)
    dMach = models.FloatField('马赫数', null=True)
    dPd = models.FloatField('动压', null=True)
    dPs = models.FloatField('静压', null=True)
    dUk = models.FloatField('航迹速度沿机体轴X轴的分量', null=True)
    dVk = models.FloatField('航迹速度沿机体轴Y轴的分量', null=True)
    dWk = models.FloatField('航迹速度沿机体轴Z轴的分量', null=True)
    dUkDot = models.FloatField('线加速度沿机体轴X轴的分量', null=True)
    dVkDot = models.FloatField('线加速度沿机体轴Y轴的分量', null=True)
    dWkDot = models.FloatField('线加速度沿机体轴Z轴的分量', null=True)
    dU = models.FloatField('空速沿机体轴X轴的分量', null=True)
    dV = models.FloatField('空速沿机体轴Y轴的分量', null=True)
    dW = models.FloatField('空速沿机体轴Z轴的分量', null=True)
    dP = models.FloatField('机体轴X轴角速度', null=True)
    dQ = models.FloatField('机体轴Y轴角速度', null=True)
    dR = models.FloatField('机体轴Z轴角速度', null=True)
    dPRad = models.FloatField('机体轴X轴角速度', null=True)
    dQRad = models.FloatField('机体轴Y轴角速度', null=True)
    dRRad = models.FloatField('机体轴Z轴角速度', null=True)
    dRDot = models.FloatField('机体轴X轴角加速度', null=True)
    dPDot = models.FloatField('机体轴Y轴角加速度', null=True)
    dQDot = models.FloatField('机体轴Z轴角加速度', null=True)
    dNx = models.FloatField('机体轴重心处X轴的过载', null=True)
    dNy = models.FloatField('机体轴重心处Y轴的过载', null=True)
    dNz = models.FloatField('机体轴重心处Z轴的过载', null=True)
    dUkgDot = models.FloatField('线加速度沿机地轴X轴的分量', null=True)
    dVkgDot = models.FloatField('线加速度沿机地轴Y轴的分量', null=True)
    dWkgDot = models.FloatField('线加速度沿机地轴Z轴的分量', null=True)
    dUkg = models.FloatField('航迹速度沿地轴系X轴速度', null=True)
    dVkg = models.FloatField('航迹速度沿地轴系Y轴速度', null=True)
    dWkg = models.FloatField('航迹速度沿地轴系Z轴速度', null=True)
    dLongitude = models.FloatField('经度', null=True)
    dLatitude = models.FloatField('纬度', null=True)
    dASL = models.FloatField('飞机重心海拔高度', null=True)
    dAGL = models.FloatField('飞机重心离地高度', null=True)
    dTrueHeading = models.FloatField('真航向', null=True)
    dMagHeading = models.FloatField('磁航向', null=True)
    dPosXg = models.FloatField('当前飞机质心在前一时刻地轴系的X轴坐标', null=True)
    dPosYg = models.FloatField('当前飞机质心在前一时刻地轴系的Y轴坐标', null=True)
    dPosZg = models.FloatField('当前飞机质心在前一时刻地轴系的Z轴坐标', null=True)
    dtx = models.FloatField('副翼偏度', null=True)
    dty = models.FloatField('方向舵偏度', null=True)
    dtz = models.FloatField('升降舵偏度', null=True)
    LGPos = models.FloatField('起落架位置', null=True)
    dFlap = models.FloatField('襟翼偏度', null=True)
    gfuel = models.FloatField('剩余油量', null=True)
    pe_t1 = models.FloatField('发动机油门杆位置1', null=True)
    pe_t2 = models.FloatField('发动机油门杆位置2', null=True)
    rot1 = models.FloatField('发动机转速1', null=True)
    rot2 = models.FloatField('发动机转速2', null=True)
    thrust = models.FloatField('发动机推力', null=True)
    gfused = models.FloatField('耗油量', null=True)
    dGtNormal = models.FloatField('燃油消耗率', null=True)
    dGfNormal = models.FloatField('燃油消耗量', null=True)
    dGFuel = models.FloatField('余油量', null=True)
    dDa = models.FloatField('横向驾驶员（滚转）操纵位置（横向杆位移）', null=True)
    dDr = models.FloatField('航向驾驶员（偏航）操纵位置（脚蹬位移）', null=True)
    dDe = models.FloatField('纵向驾驶员（俯仰）操纵位置（纵向杆位移）', null=True)
    dDaTrim = models.FloatField('配平滚转操纵量', null=True)
    dDeTrim = models.FloatField('配平俯仰操纵量', null=True)


    class Meta:
        verbose_name='QAR数据'
        verbose_name_plural='QAR数据'

    @staticmethod
    def get_fields():
        """获取QAR模型中需要导入的字段列表(排除元字段)"""
        from django.db import models  # 在方法内部导入models以避免循环导入
        exclude_fields = ['id', 'qar_id']
        return [field.name for field in QAR._meta.get_fields() 
                if (field.name not in exclude_fields) and (not field.auto_created)]
       

class QAR_Overview(models.Model):
    qar_id = models.CharField('QAR ID', max_length=60, unique=True, db_index=True)
    flight_duration = models.FloatField('飞行时长', default=0.0)
    parameter_dimension = models.IntegerField('参数维度数', default=0)
    exceed_ratio = models.FloatField('超限比例(%)', default=0.0)
    missing_ratio = models.FloatField('数据缺失比例(%)', default=0.0)
    risk_label = models.CharField('风险标签', max_length=30, default='未知')
    label = models.IntegerField('飞行状态标签', null=True, blank=True, default=0)
    record_count = models.IntegerField('记录条数', default=0)
    created_time = models.DateTimeField('创建时间', default=timezone.now)
    updated_time = models.DateTimeField('修改时间', default=timezone.now)

    class Meta:
        verbose_name = 'QAR概览'
        verbose_name_plural = 'QAR汇总'
        ordering = ['qar_id']

    def __str__(self):
        return self.qar_id

                  
class QAR_Parameter_Attribute(models.Model):
    parameter_name = models.CharField('参数名称', max_length=60, unique=True)
    description = models.TextField('参数描述', null=True, blank=True)
    unit = models.CharField('单位', max_length=30, null=True, blank=True)
    
    # 统计信息
    min_value = models.FloatField('最小值', null=True, blank=True)
    max_value = models.FloatField('最大值', null=True, blank=True)
    mean = models.FloatField('平均值', null=True, blank=True)
    variance = models.FloatField('方差', null=True, blank=True)
    normalized_variance = models.FloatField('归一化方差', null=True, blank=True)
    
    # 阈值设置
    warning_lower = models.FloatField('警告下限', null=True, blank=True, 
                                   help_text='低于此值触发警告')
    warning_upper = models.FloatField('警告上限', null=True, blank=True, 
                                   help_text='高于此值触发警告')
    critical_lower = models.FloatField('严重下限', null=True, blank=True, 
                                     help_text='低于此值触发严重警报')
    critical_upper = models.FloatField('严重上限', null=True, blank=True, 
                                     help_text='高于此值触发严重警报')
    
    # 其他信息
    is_monitored = models.BooleanField('是否监控', default=True,
                                     help_text='是否对此参数进行监控')
    updated_time = models.DateTimeField('最后更新时间', auto_now=True)
    
    class Meta:
        verbose_name = 'QAR参数属性'
        verbose_name_plural = 'QAR参数属性'
        ordering = ['parameter_name']
        
    def __str__(self):
        return f"{self.parameter_name} ({self.unit})" if self.unit else self.parameter_name
    
    def check_thresholds(self, value):
        """检查给定值是否超出阈值"""
        if value is None:
            return None
            
        alerts = []
        if self.critical_lower is not None and value < self.critical_lower:
            alerts.append('CRITICAL_LOWER')
        if self.critical_upper is not None and value > self.critical_upper:
            alerts.append('CRITICAL_UPPER')
        if self.warning_lower is not None and value < self.warning_lower:
            alerts.append('WARNING_LOWER')
        if self.warning_upper is not None and value > self.warning_upper:
            alerts.append('WARNING_UPPER')
            
        return alerts if alerts else None


class QAR_Mask(models.Model):
    qar_id = models.CharField('QAR ID', max_length=60, db_index=True)
    dSimTime = models.FloatField('模拟时间', db_index=True)
    # 约定：mask_list 与 QAR.get_fields() 顺序一致，1=观测到，0=缺失。
    mask_list = models.JSONField('缺失掩码列表', default=list)

    class Meta:
        verbose_name = 'QAR缺失掩码表'
        verbose_name_plural = 'QAR缺失掩码表'
        constraints = [
            models.UniqueConstraint(fields=['qar_id', 'dSimTime'], name='uq_core_qarmask_qid_simtime'),
        ]

    def __str__(self):
        return f"{self.qar_id}@{self.dSimTime} 缺失掩码"


class QAR_PostProcess_Task(models.Model):
    TASK_TYPE_UPLOAD = 'upload'
    TASK_TYPE_DELETE = 'delete'
    TASK_TYPE_CHOICES = [
        (TASK_TYPE_UPLOAD, '上传后处理'),
        (TASK_TYPE_DELETE, '删除后处理'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'
    STATUS_CHOICES = [
        (STATUS_PENDING, '待处理'),
        (STATUS_RUNNING, '处理中'),
        (STATUS_SUCCESS, '成功'),
        (STATUS_FAILED, '失败'),
    ]

    qar_id = models.CharField('QAR ID', max_length=60, db_index=True)
    task_type = models.CharField('任务类型', max_length=16, choices=TASK_TYPE_CHOICES, db_index=True)
    status = models.CharField('任务状态', max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    attempt_count = models.IntegerField('尝试次数', default=0)
    max_retries = models.IntegerField('最大重试次数', default=2)
    last_error = models.TextField('最后错误信息', null=True, blank=True)
    mask_min_row_id = models.BigIntegerField('掩码增量起始行ID', null=True, blank=True)
    mask_max_row_id = models.BigIntegerField('掩码增量结束行ID', null=True, blank=True)
    created_time = models.DateTimeField('创建时间', auto_now_add=True)
    started_time = models.DateTimeField('开始时间', null=True, blank=True)
    finished_time = models.DateTimeField('结束时间', null=True, blank=True)
    updated_time = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = 'QAR后处理任务'
        verbose_name_plural = 'QAR后处理任务'
        indexes = [
            models.Index(fields=['qar_id', 'task_type', 'created_time']),
            models.Index(fields=['status', 'updated_time']),
        ]

    def __str__(self):
        return f"{self.qar_id}:{self.task_type}:{self.status}"