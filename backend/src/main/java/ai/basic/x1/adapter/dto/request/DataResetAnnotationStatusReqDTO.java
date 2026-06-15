package ai.basic.x1.adapter.dto.request;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import javax.validation.constraints.NotEmpty;
import java.util.List;

/**
 * @author heojy
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class DataResetAnnotationStatusReqDTO {

    @NotEmpty(message = "dataIds cannot be null")
    private List<Long> dataIds;
}
